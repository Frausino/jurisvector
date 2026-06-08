"""Caso de uso: compressão sob demanda com persistência na coleção Chroma.

Diferença do CompressionBenchmarkUseCase:
    - Benchmark: calcula métricas, NÃO persiste na coleção Chroma.
    - Este use case: comprime E indexa na coleção comprimida correspondente.

Isso permite que o usuário escolha qual compressor aplicar a um documento
já indexado e depois use aquela coleção no retrieval do chat.

Fluxo:
    1. Recupera vetores originais do ChromaDB (coleção original).
    2. Aplica o compressor escolhido.
    3. Indexa na coleção comprimida (docuvector_int8, docuvector_binary, etc.).
    4. Para PCA: chama fit_corpus() se o store for CorpusPcaStore.
    5. Emite audit log com método e resultado.

Decisões de design:

    - Idempotência: indexar o mesmo documento duas vezes na mesma coleção
      não duplica — o ChromaVectorStore usa chunk_id como chave única.
      O chamador pode re-executar sem efeito colateral.

    - BOLA: get_vectors_for_document filtra por owner_id. A defesa é
      preservada — um usuário não consegue comprimir docs de outro tenant.

    - Stateless por documento: Int8 e Binary não precisam de fit.
      PCA/RP: o fit é feito no estado atual do CorpusPcaStore (corpus
      acumulado desde o último reinício).
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

import numpy as np

from docuvector.domain.enums import CompressionMethod
from docuvector.domain.exceptions import DocuvectorError, VectorStoreError
from docuvector.domain.interfaces import (
    AuditRepository,
    ChunkVector,
    DocumentRepository,
    VectorStore,
)
from docuvector.infrastructure.vector_stores.corpus_pca_store import CorpusPcaStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompressToCollectionInput:
    """Parâmetros para compressão sob demanda de um documento."""

    owner_id: UUID
    document_id: UUID
    document_filename: str
    compression_method: CompressionMethod


@dataclass(frozen=True, slots=True)
class CompressToCollectionResult:
    """Resultado da operação de compressão e indexação."""

    document_id: UUID
    compression_method: CompressionMethod
    chunks_indexed: int
    collection_name: str
    # Apenas para PCA: metadados do modelo treinado
    pca_explained_variance: float | None = None
    pca_model_hash: str | None = None


class CompressToCollectionUseCase:
    """Comprime vetores de um documento e persiste na coleção Chroma alvo.

    Permite que o usuário aplique um compressor específico a um documento
    já indexado, criando a cópia comprimida para uso no retrieval do chat.
    """

    def __init__(
        self,
        original_store: VectorStore,
        compressed_store: VectorStore,
        target_collection_name: str,
        document_repository: DocumentRepository | None = None,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        self._original = original_store
        self._compressed = compressed_store
        self._collection_name = target_collection_name
        self._documents = document_repository
        self._audit = audit_repository

    def compress(self, input_data: CompressToCollectionInput) -> CompressToCollectionResult:
        """Executa a compressão e indexação.

        Args:
            input_data: documento alvo e método de compressão.

        Returns:
            CompressToCollectionResult com número de chunks indexados.

        Raises:
            VectorStoreError: se os vetores originais não forem encontrados
                ou a indexação falhar.
        """
        try:
            original_vectors = self._original.get_vectors_for_document(
                owner_id=input_data.owner_id,
                document_id=input_data.document_id,
            )
        except DocuvectorError as fetch_error:
            raise VectorStoreError(
                f"Vetores originais não encontrados para o documento "
                f"'{input_data.document_filename}'. "
                "Verifique se o documento foi indexado na coleção original."
            ) from fetch_error

        matrix = np.asarray(original_vectors, dtype=np.float32)
        n_chunks = len(matrix)

        if n_chunks == 0:
            raise VectorStoreError(
                f"Documento '{input_data.document_filename}' não possui "
                "vetores na coleção original."
            )

        # Recupera textos originais do banco (PostgreSQL) para preservar
        # o conteúdo nas coleções comprimidas.
        # Sem texto: o RAG encontra o chunk mas LLM não tem contexto.
        db_chunks = (
            self._documents.list_chunks_for_document(
                owner_id=input_data.owner_id,
                document_id=input_data.document_id,
            )
            if self._documents is not None
            else []
        )
        # Mapeia chunk_index → (chunk_id, text) para lookup O(1)
        db_by_index: dict[int, tuple[UUID, str]] = {
            c.chunk_index: (c.id, c.text) for c in db_chunks
        }

        chunk_vectors = [
            ChunkVector(
                # Preserva o chunk_id original — idempotência forte.
                # Mesmo ID = Chroma faz upsert, não duplica.
                chunk_id=db_by_index[i][0] if i in db_by_index else uuid4(),
                document_id=input_data.document_id,
                owner_id=input_data.owner_id,
                chunk_index=i,
                # Texto preservado do banco — RAG funciona nas coleções comprimidas.
                text=db_by_index[i][1] if i in db_by_index else "",
                embedding=tuple(float(v) for v in matrix[i]),
                document_filename=input_data.document_filename,
            )
            for i in range(n_chunks)
        ]

        # Idempotência forte: remove vetores anteriores antes de re-indexar.
        # Garante que re-execuções não acumulam duplicatas no Chroma.
        with contextlib.suppress(DocuvectorError):
            self._compressed.delete_document(
                owner_id=input_data.owner_id,
                document_id=input_data.document_id,
            )

        self._compressed.add_chunks(chunk_vectors)

        # PCA precisa de fit explícito após add_chunks
        pca_variance: float | None = None
        pca_hash: str | None = None
        if isinstance(self._compressed, CorpusPcaStore):
            try:
                metadata = self._compressed.fit_corpus()
                pca_variance = metadata.explained_variance_ratio
                pca_hash = metadata.model_hash
                logger.info(
                    "PCA re-treinado após compressão sob demanda.",
                    extra={
                        "document_id": str(input_data.document_id),
                        "n_samples": metadata.n_samples,
                        "explained_variance": pca_variance,
                    },
                )
            except DocuvectorError as fit_error:
                logger.warning(
                    "Falha ao re-treinar PCA após compressão. "
                    "Retrieval PCA pode estar desatualizado.",
                    extra={"reason": str(fit_error)},
                )

        logger.info(
            "Documento comprimido e indexado na coleção.",
            extra={
                "document_id": str(input_data.document_id),
                "method": input_data.compression_method.value,
                "collection": self._collection_name,
                "chunks": n_chunks,
            },
        )

        return CompressToCollectionResult(
            document_id=input_data.document_id,
            compression_method=input_data.compression_method,
            chunks_indexed=n_chunks,
            collection_name=self._collection_name,
            pca_explained_variance=pca_variance,
            pca_model_hash=pca_hash,
        )
