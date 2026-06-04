"""Contrato para armazenamento e busca vetorial."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True, slots=True)
class ChunkVector:
    """Pacote (chunk + vetor) entregue ao VectorStore para indexação."""

    chunk_id: UUID
    document_id: UUID
    owner_id: UUID
    chunk_index: int
    text: str
    embedding: EmbeddingVector
    document_filename: str


class VectorStore(Protocol):
    """Armazena vetores e responde queries por similaridade.

    Toda assinatura recebe `owner_id`: o store NUNCA expõe um método
    que ignore o dono. Defesa contra BOLA built-in no contrato.
    """

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        """Indexa um lote de chunks vetorizados."""
        ...

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Busca chunks similares pertencentes ao dono informado.

        Resultados abaixo de `similarity_threshold` são descartados.
        Ordenação: similaridade decrescente.
        """
        ...

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> np.ndarray:
        """Retorna a matriz de embeddings (n_chunks, n_dims) de um documento.

        Usado pelo `CompressionBenchmarkUseCase` para recuperar os vetores
        reais antes de aplicar os compressores.

        BOLA: filtra por `owner_id` além de `document_id`. Um usuário
        que conhece o UUID de um documento alheio não consegue extrair
        os vetores desse documento.

        Raises:
            VectorStoreError: se o documento não existir ou não tiver vetores.
        """
        ...

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        """Remove todos os chunks de um documento; devolve quantidade apagada."""
        ...
