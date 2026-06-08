"""VectorStore que comprime embeddings antes de indexar.

Design (composição, não herança):

    CompressedVectorStore
        └── ChromaVectorStore          (armazena os vetores comprimidos)
        └── Compressor                 (transforma float32 → int8/binary/pca)

Por que composição:
    - `ChromaVectorStore` já faz persistência, telemetria e BOLA.
    - `CompressedVectorStore` só adiciona a camada de transformação.
    - Trocar o storage (ex.: Pinecone) não exige mudar o compressor.

Contrato de BOLA: todas as operações delegam ao `ChromaVectorStore`
subjacente, que já filtra por `owner_id`. Nenhuma defesa é removida.

Limitações documentadas (Sprint 6, escopo TCC):
    - `get_vectors_for_document` retorna os vetores COMPRIMIDOS (não originais).
      Para reconstrução exata precisaríamos do fator de escala (Int8) ou
      desempacotamento (Binary). Suficiente para o benchmark comparativo.
    - Binary: saída uint8; distância coseno ainda funciona, mas a métrica
      é menos precisa que com float32.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces import ChunkVector, VectorStore
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector
from docuvector.infrastructure.compression.binary_compressor import BinaryCompressor
from docuvector.infrastructure.compression.int8_compressor import Int8Compressor
from docuvector.infrastructure.compression.pca_compressor import PcaCompressor
from docuvector.infrastructure.compression.random_projection_compressor import (
    RandomProjectionCompressor,
)

logger = logging.getLogger(__name__)

# Tipos que precisam de fit antes de transform (stateful).


@runtime_checkable
class _Compressor(Protocol):
    """Protocolo mínimo de um compressor de embedding."""

    def fit(self, matrix: NDArray[np.float32]) -> None: ...
    def transform(self, matrix: NDArray[np.float32]) -> NDArray[np.float32]: ...


_STATEFUL_COMPRESSOR_TYPES = (PcaCompressor, RandomProjectionCompressor)
_AnyCompressor = PcaCompressor | RandomProjectionCompressor | Int8Compressor | BinaryCompressor


class CompressedVectorStore:
    """Wrapper que comprime embeddings antes de gravar e transforma queries antes de buscar.

    O compressor é ajustado (fit) no primeiro batch de `add_chunks` usando
    os vetores daquele documento. Compressores stateless (Int8, Binary)
    ignoram o fit e transformam diretamente.

    Uso no pipeline de ingestão:
        store = CompressedVectorStore(chroma, Int8Compressor())
        store.add_chunks(chunk_vectors)  # comprime e indexa

    Uso no retrieval:
        results = store.search(owner_id, query_embedding, top_k, threshold)
        # query_embedding é comprimido com o mesmo compressor antes da busca
    """

    def __init__(
        self,
        inner_store: VectorStore,
        compressor: _AnyCompressor,
    ) -> None:
        self._inner: VectorStore = inner_store
        self._compressor = compressor

    # ------------------------------------------------------------------
    # Implementação do protocolo VectorStore
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        """Comprime os embeddings e delega ao ChromaVectorStore."""
        if not chunks:
            return

        raw_matrix = np.array(
            [list(chunk.embedding) for chunk in chunks],
            dtype=np.float32,
        )

        compressed_matrix = self._compress_matrix(raw_matrix)

        compressed_chunks = [
            ChunkVector(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                owner_id=chunk.owner_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding=tuple(float(v) for v in compressed_matrix[i]),
                document_filename=chunk.document_filename,
            )
            for i, chunk in enumerate(chunks)
        ]
        self._inner.add_chunks(compressed_chunks)

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Comprime a query antes de buscar, garantindo espaço vetorial consistente."""
        query_array = np.array(list(query_embedding), dtype=np.float32).reshape(1, -1)
        compressed_query = self._compress_matrix(query_array)
        compressed_embedding: EmbeddingVector = tuple(float(v) for v in compressed_query[0])
        return self._inner.search(
            owner_id=owner_id,
            query_embedding=compressed_embedding,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        """Retorna vetores comprimidos persistidos (não os originais)."""
        return self._inner.get_vectors_for_document(owner_id, document_id)

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        """Delega diretamente: BOLA preservado pelo ChromaVectorStore interno."""
        return self._inner.delete_document(owner_id, document_id)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _compress_matrix(self, matrix: NDArray[np.float32]) -> NDArray[np.float32]:
        """Aplica fit+transform ou só transform dependendo do tipo de compressor."""
        try:
            if isinstance(self._compressor, _STATEFUL_COMPRESSOR_TYPES):
                # Stateful: fit expõe a distribuição dos dados. Em produção
                # o fit seria feito uma vez e serializado. Aqui fazemos
                # fit por batch (simples e suficiente para TCC).
                self._compressor.fit(matrix)

            compressed = self._compressor.transform(matrix)
            return np.asarray(compressed, dtype=np.float32)

        except Exception as compressor_failure:
            raise VectorStoreError(
                f"Falha ao comprimir embeddings: {compressor_failure}"
            ) from compressor_failure
