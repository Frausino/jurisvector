"""Extensão do IngestionUseCase para múltiplas coleções Chroma.

Motivação:
    O benchmark de compressão (Sprint 4A) calcula *métricas* sobre
    vetores comprimidos, mas não os persiste em coleções separadas.
    Para comparar a qualidade do retrieval entre compressores, precisamos
    que cada coleção Chroma contenha os vetores no espaço comprimido
    correspondente.

Design (aberto/fechado — OCP):
    - `IngestionUseCase` não é modificado.
    - `MultiCollectionIngestionUseCase` compõe o use case original e
      adiciona a etapa de gravação nas coleções extras APÓS o sucesso
      do pipeline principal.
    - Falha em uma coleção comprimida é registrada em log e NÃO aborta
      a ingestão — o documento fica disponível via retrieval na coleção
      original. O benchmark pode ser re-executado.

Ordem de operações:
    1. `IngestionUseCase.ingest(...)` → documento EMBEDDED na coleção original.
    2. Para cada (compressor, vector_store) extra:
       a. `get_vectors_for_document` recupera os vetores originais.
       b. `CompressedVectorStore.add_chunks` comprime e indexa.
    3. Retorna `MultiCollectionIngestionResult` com `side_collection_errors`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import numpy as np

from docuvector.application.ingestion_use_case import IngestionResult, IngestionUseCase
from docuvector.domain.entities import AuditEvent
from docuvector.domain.enums import AuditAction, AuditStatus, CompressionMethod
from docuvector.domain.exceptions import DocuvectorError
from docuvector.domain.interfaces import (
    AuditRepository,
    ChunkVector,
    DocumentRepository,
    EmbeddingProvider,
    VectorStore,
)
from docuvector.infrastructure.vector_stores.corpus_pca_store import (
    CorpusPcaStore,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SideCollectionError:
    """Erro isolado de uma coleção comprimida. Não aborta a ingestão."""

    method: CompressionMethod
    reason: str


@dataclass(frozen=True, slots=True)
class MultiCollectionIngestionResult:
    """Resultado da ingestão com múltiplas coleções.

    `primary_result` é o resultado da coleção original.
    `side_collection_errors` lista falhas de coleções comprimidas, se houver.
    """

    primary_result: IngestionResult
    side_collection_errors: tuple[SideCollectionError, ...] = field(default_factory=tuple)

    @property
    def all_collections_succeeded(self) -> bool:
        """True se todas as coleções comprimidas foram indexadas com sucesso."""
        return not self.side_collection_errors


class MultiCollectionIngestionUseCase:
    """Pipeline de ingestão que grava em múltiplas coleções Chroma.

    Grava na coleção original e, em seguida, nas coleções comprimidas
    (Int8, Binary, PCA, RandomProjection). Cada coleção comprimida
    representa um espaço vetorial diferente — o que permite comparar
    a qualidade do retrieval entre eles no dashboard.
    """

    def __init__(
        self,
        primary_ingestion: IngestionUseCase,
        primary_vector_store: VectorStore,
        compressed_stores: list[tuple[CompressionMethod, VectorStore]],
        document_repository: DocumentRepository,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        """
        Args:
            primary_ingestion: use case original, sem modificação.
            primary_vector_store: coleção original (float32).
            compressed_stores: lista de (método, store comprimido).
                Ex.: [(CompressionMethod.INT8, int8_store), ...]
            document_repository: para recuperar chunks após ingestão primária.
        """
        self._primary = primary_ingestion
        self._primary_store = primary_vector_store
        self._compressed_stores = compressed_stores
        self._documents = document_repository
        self._audit = audit_repository

    def ingest(
        self,
        owner_id: UUID,
        filename: str,
        content: bytes,
        embedding_provider: EmbeddingProvider,
        client_ip: str | None,
        user_agent: str | None,
    ) -> MultiCollectionIngestionResult:
        """Ingere o documento APENAS na coleção original (float32).

        Decisão de design: compressão é sob demanda, não automática.
        O usuário escolhe qual compressor aplicar a cada documento
        via menu na sidebar (CompressToCollectionUseCase).

        Motivação:
            - PCA com corpus pequeno gera dims=1 (inútil).
            - Nem todo documento precisa de todas as coleções.
            - O usuário deve ter controle sobre onde indexa.
        """
        primary_result = self._primary.ingest(
            owner_id=owner_id,
            filename=filename,
            content=content,
            embedding_provider=embedding_provider,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        result = MultiCollectionIngestionResult(
            primary_result=primary_result,
            side_collection_errors=(),
        )
        self._emit_audit(result)
        return result

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _emit_audit(self, result: MultiCollectionIngestionResult) -> None:
        """Registra o resultado da ingestão multi-coleção no audit log."""
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent(
                actor_user_id=result.primary_result.document.owner_id,
                action=AuditAction.DOCUMENT_UPLOADED,
                status=AuditStatus.SUCCESS,
                resource_type="document",
                resource_id=result.primary_result.document.id,
                metadata={
                    "benchmark_type": "multi_collection_ingestion",
                    "chunks_created": result.primary_result.chunks_created,
                    "compressed_collections_ok": (
                        len(self._compressed_stores) - len(result.side_collection_errors)
                    ),
                    "compressed_collections_failed": len(result.side_collection_errors),
                    "failed_methods": [e.method.value for e in result.side_collection_errors],
                },
            )
        )

    def _replicate_to_compressed_stores(
        self,
        owner_id: UUID,
        document_id: UUID,
        document_filename: str,
        embedding_provider: EmbeddingProvider,
    ) -> list[SideCollectionError]:
        """Recupera vetores originais e indexa em cada coleção comprimida."""
        errors: list[SideCollectionError] = []

        try:
            original_vectors = self._primary_store.get_vectors_for_document(
                owner_id=owner_id,
                document_id=document_id,
            )
        except DocuvectorError as fetch_error:
            logger.exception(
                "Falha ao recuperar vetores originais para replicação. "
                "Coleções comprimidas não serão populadas.",
                extra={"document_id": str(document_id)},
            )
            return [
                SideCollectionError(method=method, reason=str(fetch_error))
                for method, _ in self._compressed_stores
            ]

        chunk_vectors = self._build_chunk_vectors(
            original_vectors=original_vectors,
            owner_id=owner_id,
            document_id=document_id,
            document_filename=document_filename,
        )

        for method, compressed_store in self._compressed_stores:
            try:
                compressed_store.add_chunks(chunk_vectors)
                logger.info(
                    "Coleção comprimida indexada com sucesso.",
                    extra={"method": method.value, "document_id": str(document_id)},
                )
            except DocuvectorError as store_error:
                logger.warning(
                    "Falha ao indexar coleção comprimida. "
                    "Retrieval nesta coleção indisponível para este documento.",
                    extra={"method": method.value, "reason": str(store_error)},
                )
                errors.append(SideCollectionError(method=method, reason=str(store_error)))

        # Treina PCA global após bufferizar todos os chunks das coleções PCA.
        # fit_corpus() deve ser chamado após add_chunks() de TODOS os documentos
        # do batch para garantir espaço vetorial consistente (ver CorpusPcaStore).
        self._fit_pca_stores(errors)

        return errors

    def _fit_pca_stores(self, errors: list[SideCollectionError]) -> None:
        """Chama fit_corpus() em todas as coleções PCA com dados pendentes.

        Chamado após o loop de add_chunks para garantir que o PCA é
        treinado com todos os vetores do batch antes da primeira busca.
        Falhas de fit são isoladas — não abortam o resultado da ingestão.
        """
        failed_methods = {e.method for e in errors}
        for method, compressed_store in self._compressed_stores:
            if method in failed_methods:
                continue  # já falhou no add_chunks, não tentar fit
            if not isinstance(compressed_store, CorpusPcaStore):
                continue  # apenas CorpusPcaStore precisa de fit explícito
            try:
                metadata = compressed_store.fit_corpus()
                logger.info(
                    "PCA global treinado após ingestão.",
                    extra={
                        "method": method.value,
                        "n_samples": metadata.n_samples,
                        "explained_variance": metadata.explained_variance_ratio,
                        "model_hash": metadata.model_hash[:12],
                    },
                )
            except DocuvectorError as fit_error:
                logger.warning(
                    "Falha ao treinar PCA global. Retrieval PCA indisponível.",
                    extra={"method": method.value, "reason": str(fit_error)},
                )
                errors.append(SideCollectionError(method=method, reason=str(fit_error)))

    @staticmethod
    def _build_chunk_vectors(
        original_vectors: object,
        owner_id: UUID,
        document_id: UUID,
        document_filename: str,
    ) -> list[ChunkVector]:
        """Monta ChunkVectors a partir da matriz de vetores originais.

        IDs são derivados do índice (sem banco de dados). O compressed_store
        só precisa dos vetores — o texto original vem do ChromaDB original
        quando o retrieval for feito.
        """

        matrix = np.asarray(original_vectors, dtype=np.float32)
        return [
            ChunkVector(
                chunk_id=uuid4(),
                document_id=document_id,
                owner_id=owner_id,
                chunk_index=i,
                text="",  # texto não é re-indexado nas coleções comprimidas
                embedding=tuple(float(v) for v in matrix[i]),
                document_filename=document_filename,
            )
            for i in range(len(matrix))
        ]
