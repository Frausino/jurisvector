"""Caso de uso: benchmark de compressão de embeddings.

Orquestra os 4 compressores (PCA, RandomProjection, Int8, Binary) sobre
os embeddings reais de um documento, mede retenção semântica e bytes
economizados, e persiste o melhor resultado no banco.

Fluxo:

    find_by_id_for_owner(owner_id, document_id)
        |
        v
    get_vectors_for_document(owner_id, document_id)  ← Chroma
        |
        v
    [para cada compressor]:
        fit(X) → transform(X) → compute_semantic_retention(X, X')
        → CompressionMetrics
        |
        v
    seleciona best = max(results, key=retention)
        |
        v
    update_compression_metrics(owner_id, document_id, best)  ← Postgres
        |
        v
    AuditRepository.append(DOCUMENT_UPDATED, metadata={...})
        |
        v
    retorna list[CompressionMetrics] ordenado por retention desc

Decisões de design:

1.  **Sem import de sklearn aqui.** Compressores chegam via Protocol;
    o use case só enxerga `Compressor.fit / .transform / .bytes_per_element`.
    Novo compressor = novo arquivo em `infrastructure/compression/`,
    sem tocar no use case.

2.  **Pearson de cosine_sim_matrix**, não de normas. Mede preservação
    da estrutura relativa entre chunks, que é o que importa para RAG.
    Detalhes em `_compute_semantic_retention`.

3.  **`max_pairs = 200`** para conter o custo O(n²) de pares coseno.
    Documentos com muitos chunks amostram aleatoriamente.

4.  **Falha isolada por compressor.** Se um compressor lançar exceção
    (ex.: n_samples < target_dim para PCA), o use case registra o erro
    em log, continua com os demais e não aborta o benchmark inteiro.
    O usuário pode ter um documento muito pequeno; seria pior travar tudo.

5.  **`ingest_time_ms` no banco** = fit_time_ms + transform_time_ms do
    melhor compressor. Não é o tempo do pipeline de upload; é o tempo
    do passo de compressão que o benchmark mediu.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import numpy as np
import scipy.stats

from docuvector.domain.entities import AuditEvent, Document
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.enums import AuditAction, AuditStatus
from docuvector.domain.exceptions import ResourceNotFoundError, VectorStoreError
from docuvector.domain.interfaces import AuditRepository, DocumentRepository, VectorStore
from docuvector.domain.interfaces.compressor import Compressor
from docuvector.infrastructure.compression import build_all_compressors

logger = logging.getLogger(__name__)

_RESOURCE_TYPE = "document"
_BENCHMARK_ACTION_METADATA_KEY = "benchmark_type"
_BENCHMARK_ACTION_METADATA_VALUE = "compression"
_MAX_COSINE_PAIRS = 200  # limite para O(n²) da Pearson de cosine sims


@dataclass(frozen=True, slots=True)
class BenchmarkInput:
    """Parâmetros de entrada do benchmark de compressão."""

    owner_id: UUID
    document_id: UUID
    target_dim: int | None = None  # None → usa original_dim // 2


class CompressionBenchmarkUseCase:
    """Benchmarca os 4 compressores e persiste o melhor resultado."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStore,
        audit_repository: AuditRepository,
    ) -> None:
        self._documents = document_repository
        self._vectors = vector_store
        self._audit = audit_repository

    def run(self, benchmark_input: BenchmarkInput) -> list[CompressionMetrics]:
        """Executa o benchmark e retorna os resultados de todos os compressores.

        Returns:
            Lista de CompressionMetrics ordenada por semantic_retention desc.
            Compressores que falharam não aparecem na lista.

        Raises:
            ResourceNotFoundError: se o documento não existir para este owner.
            VectorStoreError: se não houver vetores indexados.
        """
        document = self._require_document(
            benchmark_input.owner_id,
            benchmark_input.document_id,
        )
        embedding_matrix = self._vectors.get_vectors_for_document(
            owner_id=benchmark_input.owner_id,
            document_id=benchmark_input.document_id,
        )

        original_dim = embedding_matrix.shape[1]
        target_dim = benchmark_input.target_dim or (original_dim // 2)
        target_dim = min(target_dim, embedding_matrix.shape[0] - 1, original_dim - 1)
        target_dim = max(1, target_dim)

        compressors = build_all_compressors(target_dim=target_dim)
        results = self._run_all_compressors(
            compressors=compressors,
            embedding_matrix=embedding_matrix,
        )

        if not results:
            raise VectorStoreError(
                "Nenhum compressor produziu resultado válido para o documento "
                f"{benchmark_input.document_id}. Verifique os logs."
            )

        best = max(results, key=lambda m: m.semantic_retention)

        updated_document = self._documents.update_compression_metrics(
            owner_id=benchmark_input.owner_id,
            document_id=benchmark_input.document_id,
            metrics=best,
        )

        self._emit_audit(
            owner_id=benchmark_input.owner_id,
            document=updated_document or document,
            results=results,
            best=best,
        )

        return sorted(results, key=lambda m: m.semantic_retention, reverse=True)

    # ------------------------------------------------------------------
    # Orquestração dos compressores
    # ------------------------------------------------------------------
    def _run_all_compressors(
        self,
        compressors: Sequence[Compressor],
        embedding_matrix: np.ndarray,
    ) -> list[CompressionMetrics]:
        results: list[CompressionMetrics] = []
        for compressor in compressors:
            try:
                metrics = self._benchmark_one(compressor, embedding_matrix)
                results.append(metrics)
            except Exception as compressor_failure:
                logger.warning(
                    "Compressor %s falhou: %s",
                    compressor.method_name.value,
                    compressor_failure,
                    exc_info=True,
                )
        return results

    def _benchmark_one(
        self,
        compressor: Compressor,
        embedding_matrix: np.ndarray,
    ) -> CompressionMetrics:
        """Executa fit + transform + Pearson para um compressor."""
        n_vectors, original_dim = embedding_matrix.shape

        fit_start = time.perf_counter()
        compressor.fit(embedding_matrix)
        fit_time_ms = int((time.perf_counter() - fit_start) * 1000)

        transform_start = time.perf_counter()
        compressed_matrix = compressor.transform(embedding_matrix)
        transform_time_ms = int((time.perf_counter() - transform_start) * 1000)

        compressed_dim = compressed_matrix.shape[1]
        semantic_retention = _compute_semantic_retention(
            original=embedding_matrix,
            compressed=compressed_matrix,
            max_pairs=_MAX_COSINE_PAIRS,
        )

        return CompressionMetrics(
            method=compressor.method_name,
            original_dim=original_dim,
            compressed_dim=compressed_dim,
            bytes_per_element=compressor.bytes_per_element,
            fit_time_ms=fit_time_ms,
            transform_time_ms=transform_time_ms,
            semantic_retention=semantic_retention,
            n_vectors=n_vectors,
        )

    # ------------------------------------------------------------------
    # Validação de pré-condições
    # ------------------------------------------------------------------
    def _require_document(self, owner_id: UUID, document_id: UUID) -> Document:
        document = self._documents.find_by_id_for_owner(
            owner_id=owner_id,
            document_id=document_id,
        )
        if document is None:
            raise ResourceNotFoundError(
                f"Documento {document_id} não encontrado para este usuário."
            )
        return document

    # ------------------------------------------------------------------
    # Auditoria
    # ------------------------------------------------------------------
    def _emit_audit(
        self,
        owner_id: UUID,
        document: Document,
        results: list[CompressionMetrics],
        best: CompressionMetrics,
    ) -> None:
        self._audit.append(
            AuditEvent(
                actor_user_id=owner_id,
                action=AuditAction.DOCUMENT_UPDATED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=document.id,
                metadata={
                    _BENCHMARK_ACTION_METADATA_KEY: _BENCHMARK_ACTION_METADATA_VALUE,
                    "compressors_tested": len(results),
                    "best_method": best.method.value,
                    "best_retention": best.semantic_retention,
                    "best_ratio_bytes": best.ratio_bytes,
                    "best_space_savings_pct": best.space_savings_pct,
                    "original_dim": best.original_dim,
                    "compressed_dim": best.compressed_dim,
                    "n_vectors": best.n_vectors,
                },
            )
        )


# ------------------------------------------------------------------
# Função pura: Pearson de cosine similarities
# Fora da classe para ser testável isoladamente e reutilizável.
# ------------------------------------------------------------------
MIN_VECTORS_FOR_PAIRWISE_COMPARISON = 2


def _compute_semantic_retention(
    original: np.ndarray,
    compressed: np.ndarray,
    max_pairs: int = _MAX_COSINE_PAIRS,
) -> float:
    """Correlação de Pearson entre matrizes de similaridade coseno.

    Mede se a estrutura relativa entre vetores foi preservada após
    compressão — o que importa para RAG: se dois chunks eram similares
    antes, ainda são similares depois?

    Algoritmo:
        1. Normaliza L2 ambas as matrizes (vetores unitários).
        2. Calcula cosine_sim = dot product para todos os pares (i, j) com i < j.
        3. Se n_pares > max_pairs, amostra aleatoriamente.
        4. Pearson(cos_original, cos_compressed).
        5. Clip para [0, 1]: correlação negativa não tem interpretação útil aqui.

    Args:
        original:   (n, d_orig) float32
        compressed: (n, d_comp) any dtype compatível com float64
        max_pairs:  número máximo de pares para conter custo O(n²)

    Returns:
        Retenção semântica em [0.0, 1.0].
    """

    n = original.shape[0]
    # Com um único vetor não há pares; retorna 1.0 (trivialmente preservado).
    if n < MIN_VECTORS_FOR_PAIRWISE_COMPARISON:
        return 1.0

    eps = 1e-8

    orig_f = original.astype(np.float64)
    comp_f = compressed.astype(np.float64)

    orig_norm = orig_f / (np.linalg.norm(orig_f, axis=1, keepdims=True) + eps)
    comp_norm = comp_f / (np.linalg.norm(comp_f, axis=1, keepdims=True) + eps)

    idx_i, idx_j = np.triu_indices(n, k=1)
    n_pairs = len(idx_i)

    if n_pairs > max_pairs:
        rng = np.random.default_rng(seed=0)
        sample = rng.choice(n_pairs, size=max_pairs, replace=False)
        idx_i = idx_i[sample]
        idx_j = idx_j[sample]

    cos_orig = np.sum(orig_norm[idx_i] * orig_norm[idx_j], axis=1)
    cos_comp = np.sum(comp_norm[idx_i] * comp_norm[idx_j], axis=1)

    if (
        len(cos_orig) < MIN_VECTORS_FOR_PAIRWISE_COMPARISON
        or len(cos_comp) < MIN_VECTORS_FOR_PAIRWISE_COMPARISON
    ):
        return 1.0

    correlation, _ = scipy.stats.pearsonr(cos_orig, cos_comp)

    corr = cast(float, correlation)

    if np.isnan(corr):
        return 1.0

    return float(np.clip(corr, 0.0, 1.0))
