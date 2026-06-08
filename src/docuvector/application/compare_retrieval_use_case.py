"""Caso de uso: comparação de retrieval entre coleções com métricas IR padrão.

Métricas implementadas (padrão Information Retrieval):

    Recall@K
        Fração dos documentos relevantes que aparecem nos top-K resultados.
        Relevante = recuperado pela coleção original (ground truth).
        Recall@K = |S_compressed ∩ S_original| / |S_original|

    Precision@K
        Fração dos top-K resultados que são relevantes.
        Precision@K = |S_compressed ∩ S_original| / K

    MRR (Mean Reciprocal Rank)
        Recíproco da posição do primeiro documento relevante.
        MRR = 1/rank_do_primeiro_relevante (0 se nenhum é relevante).
        Mede: "quão cedo o sistema encontra um documento relevante?"

Referência:
    Manning, C., Raghavan, P., Schütze, H. (2008).
    Introduction to Information Retrieval. Cambridge University Press.
    Cap. 8: Evaluation in information retrieval.

Decisões de design:

    Ground truth = coleção original.
    A coleção original (float32 sem compressão) é o padrão de qualidade.
    Métricas medem quanto cada compressor se afasta desse padrão.

    Auditoria opcional.
    O benchmark comparativo registra no audit log para rastreabilidade.
    Caller passa None para desabilitar (ex.: testes de unidade).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from docuvector.domain.entities import AuditEvent, RetrievedChunk
from docuvector.domain.enums import AuditAction, AuditStatus, CompressionMethod
from docuvector.domain.exceptions import ValidationError
from docuvector.domain.interfaces import AuditRepository, EmbeddingProvider, VectorStore

logger = logging.getLogger(__name__)

_MIN_QUERY_LENGTH = 3
_COMPARISON_TOP_K = 5
_COMPARISON_THRESHOLD = 0.0  # sem filtro: queremos ver todos os candidatos
_RESOURCE_TYPE = "retrieval_comparison"

# Chave de auditoria — nomeada para evitar drift (GAP 6)
_AUDIT_KEY_BENCHMARK_TYPE = "benchmark_type"
_AUDIT_VALUE_RETRIEVAL_COMPARISON = "retrieval_comparison"
_AUDIT_KEY_RECALL_AT_K = "recall_at_k"
_AUDIT_KEY_PRECISION_AT_K = "precision_at_k"
_AUDIT_KEY_MRR = "mrr"
_AUDIT_KEY_PCA_HASH = "pca_model_hash"


@dataclass(frozen=True, slots=True)
class IrMetrics:
    """Métricas de Information Retrieval para uma coleção comprimida.

    Calculadas tendo a coleção original como ground truth.
    """

    recall_at_k: float  # [0, 1] — 1.0 = recuperou todos os relevantes
    precision_at_k: float  # [0, 1] — 1.0 = todos os resultados são relevantes
    mrr: float  # [0, 1] — 1.0 = relevante na posição 1


@dataclass(frozen=True, slots=True)
class CollectionRetrievalResult:
    """Resultado de uma coleção individual no benchmark comparativo."""

    collection_name: str
    compression_method: CompressionMethod | None  # None = original
    chunks: tuple[RetrievedChunk, ...]
    avg_similarity: float
    latency_ms: int
    chunks_count: int
    ir_metrics: IrMetrics = field(
        default_factory=lambda: IrMetrics(
            recall_at_k=1.0,
            precision_at_k=1.0,
            mrr=1.0,
        )
    )


@dataclass(frozen=True, slots=True)
class CompareRetrievalResult:
    """Resultado completo da comparação entre todas as coleções."""

    query: str
    original: CollectionRetrievalResult
    compressed: tuple[CollectionRetrievalResult, ...]


class CompareRetrievalUseCase:
    """Compara qualidade de retrieval entre a coleção original e as comprimidas.

    Métricas: Recall@K, Precision@K, MRR.
    Ground truth: chunks recuperados pela coleção original.
    """

    def __init__(
        self,
        original_store: VectorStore,
        compressed_stores: list[tuple[CompressionMethod, VectorStore]],
        audit_repository: AuditRepository | None = None,
    ) -> None:
        self._original_store = original_store
        self._compressed_stores = compressed_stores
        self._audit = audit_repository

    def compare(
        self,
        owner_id: UUID,
        query: str,
        embedding_provider: EmbeddingProvider,
        top_k: int = _COMPARISON_TOP_K,
    ) -> CompareRetrievalResult:
        """Executa a query em todas as coleções e retorna métricas IR.

        Args:
            owner_id: isolamento por tenant (BOLA propagado a cada store).
            query: pergunta em linguagem natural.
            embedding_provider: embedder para vetorizar a query.
            top_k: número de resultados por coleção.

        Raises:
            ValidationError: query muito curta ou só whitespace.
        """
        if len(query.strip()) < _MIN_QUERY_LENGTH:
            raise ValidationError(f"Query deve ter no mínimo {_MIN_QUERY_LENGTH} caracteres.")

        query_embedding = embedding_provider.embed_query(query)

        original_result = self._retrieve_one(
            store=self._original_store,
            collection_name="original",
            compression_method=None,
            owner_id=owner_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        # document_ids da coleção original = ground truth
        original_doc_ids: set[str] = {str(chunk.document_id) for chunk in original_result.chunks}

        compressed_results: list[CollectionRetrievalResult] = []
        for method, store in self._compressed_stores:
            raw_result = self._retrieve_one(
                store=store,
                collection_name=method.value,
                compression_method=method,
                owner_id=owner_id,
                query_embedding=query_embedding,
                top_k=top_k,
            )
            ir = _compute_ir_metrics(
                retrieved=raw_result.chunks,
                ground_truth_doc_ids=original_doc_ids,
                top_k=top_k,
            )
            compressed_results.append(
                CollectionRetrievalResult(
                    collection_name=raw_result.collection_name,
                    compression_method=raw_result.compression_method,
                    chunks=raw_result.chunks,
                    avg_similarity=raw_result.avg_similarity,
                    latency_ms=raw_result.latency_ms,
                    chunks_count=raw_result.chunks_count,
                    ir_metrics=ir,
                )
            )

        result = CompareRetrievalResult(
            query=query,
            original=original_result,
            compressed=tuple(compressed_results),
        )

        if self._audit is not None:
            self._emit_audit(owner_id=owner_id, result=result)

        return result

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _retrieve_one(
        store: VectorStore,
        collection_name: str,
        compression_method: CompressionMethod | None,
        owner_id: UUID,
        query_embedding: Sequence[float],
        top_k: int,
    ) -> CollectionRetrievalResult:
        start = time.perf_counter()
        try:
            chunks = store.search(
                owner_id=owner_id,
                query_embedding=tuple(query_embedding),
                top_k=top_k,
                similarity_threshold=_COMPARISON_THRESHOLD,
            )
        except Exception as store_failure:
            logger.warning(
                "Falha ao buscar na coleção %s: %s",
                collection_name,
                store_failure,
            )
            chunks = []

        latency_ms = int((time.perf_counter() - start) * 1000)
        avg_similarity = sum(c.similarity for c in chunks) / len(chunks) if chunks else 0.0

        return CollectionRetrievalResult(
            collection_name=collection_name,
            compression_method=compression_method,
            chunks=tuple(chunks),
            avg_similarity=avg_similarity,
            latency_ms=latency_ms,
            chunks_count=len(chunks),
        )

    def _emit_audit(
        self,
        owner_id: UUID,
        result: CompareRetrievalResult,
    ) -> None:
        if self._audit is None:
            return

        metrics_by_method = {
            r.compression_method.value if r.compression_method else "original": {
                _AUDIT_KEY_RECALL_AT_K: r.ir_metrics.recall_at_k,
                _AUDIT_KEY_PRECISION_AT_K: r.ir_metrics.precision_at_k,
                _AUDIT_KEY_MRR: r.ir_metrics.mrr,
                "avg_similarity": r.avg_similarity,
                "latency_ms": r.latency_ms,
            }
            for r in (*result.compressed,)
        }

        self._audit.append(
            AuditEvent(
                actor_user_id=owner_id,
                action=AuditAction.QUERY_EXECUTED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                metadata={
                    _AUDIT_KEY_BENCHMARK_TYPE: _AUDIT_VALUE_RETRIEVAL_COMPARISON,
                    "query_length": len(result.query),
                    "original_chunks": result.original.chunks_count,
                    "compressed_collections": len(result.compressed),
                    "metrics_by_method": metrics_by_method,
                },
            )
        )


# ------------------------------------------------------------------
# Funções puras de métricas IR (testáveis isoladamente)
# ------------------------------------------------------------------


def _compute_ir_metrics(
    retrieved: Sequence[RetrievedChunk],
    ground_truth_doc_ids: set[str],
    top_k: int,
) -> IrMetrics:
    """Calcula Recall@K, Precision@K e MRR.

    Ground truth: document_ids retornados pela coleção original.

    Args:
        retrieved: chunks retornados pela coleção comprimida.
        ground_truth_doc_ids: document_ids do ground truth (coleção original).
        top_k: K para as métricas @K.
    """
    if not ground_truth_doc_ids:
        return IrMetrics(recall_at_k=1.0, precision_at_k=1.0, mrr=1.0)

    top_k_retrieved = list(retrieved[:top_k])
    retrieved_doc_ids = [str(c.document_id) for c in top_k_retrieved]

    # Usa document_ids únicos para evitar dupla contagem de chunks
    # do mesmo documento (causa do Recall > 100%).
    unique_retrieved_ids = list(dict.fromkeys(retrieved_doc_ids))

    relevant_in_top_k = sum(1 for doc_id in unique_retrieved_ids if doc_id in ground_truth_doc_ids)

    # Cap em 1.0: Recall e Precision são métricas no intervalo [0, 1].
    recall = min(relevant_in_top_k / len(ground_truth_doc_ids), 1.0)
    precision = min(
        relevant_in_top_k / len(unique_retrieved_ids) if unique_retrieved_ids else 0.0,
        1.0,
    )

    # MRR: recíproco do rank do primeiro documento relevante único
    mrr = 0.0
    for rank, doc_id in enumerate(unique_retrieved_ids, start=1):
        if doc_id in ground_truth_doc_ids:
            mrr = 1.0 / rank
            break

    return IrMetrics(
        recall_at_k=round(recall, 4),
        precision_at_k=round(precision, 4),
        mrr=round(mrr, 4),
    )
