"""Endpoints REST de métricas e benchmarks operacionais."""

from __future__ import annotations

from fastapi import APIRouter, status

from docuvector.api.deps import (
    CurrentTokenDependency,
    EmbeddingBenchmarkUseCaseDependency,
    MetricsUseCaseDependency,
)
from docuvector.api.schemas.metrics import (
    CompressionStatsResponse,
    DashboardResponse,
    DocumentStatsResponse,
    EmbeddingBenchmarkRequest,
    EmbeddingBenchmarkResponse,
    EmbeddingProviderBenchmarkItem,
    LlmProviderStatsResponse,
    StorageSavingsResponse,
)
from docuvector.application.metrics_use_case import StorageSavings

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


# =============================================================
# GET /api/v1/metrics/dashboard
# =============================================================
@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Dashboard de KPIs operacionais",
    description=(
        "Agrega `audit_logs.metadata` em KPIs: latência por provider LLM, "
        "custo USD acumulado, retenção semântica por compressor e economia "
        "de armazenamento estimada em Pinecone/Qdrant (USD e R$).\\n\\n"
        "Todos os dados são filtrados pelo `owner_id` do token — "
        "o usuário vê apenas suas próprias métricas."
    ),
)
def get_dashboard(
    token_payload: CurrentTokenDependency,
    metrics_use_case: MetricsUseCaseDependency,
) -> DashboardResponse:
    data = metrics_use_case.get_dashboard(owner_id=token_payload.user_id)

    return DashboardResponse(
        llm_stats=[
            LlmProviderStatsResponse(
                provider=s.provider,
                total_calls=s.total_calls,
                avg_latency_ms=s.avg_latency_ms,
                p95_latency_ms=s.p95_latency_ms,
                total_tokens=s.total_tokens,
                total_cost_usd=s.total_cost_usd,
            )
            for s in data.llm_stats
        ],
        compression_stats=[
            CompressionStatsResponse(
                method=s.method,
                avg_semantic_retention=s.avg_semantic_retention,
                avg_space_savings_pct=s.avg_space_savings_pct,
            )
            for s in data.compression_stats
        ],
        document_stats=DocumentStatsResponse(
            total=data.document_stats.total,
            embedded=data.document_stats.embedded,
            failed=data.document_stats.failed,
            processing=data.document_stats.processing,
        ),
        storage_savings=_serialize_storage_savings(data.storage_savings),
        total_queries=data.total_queries,
        total_cost_usd=data.total_cost_usd,
        total_cost_brl=data.total_cost_brl,
    )


# =============================================================
# POST /api/v1/metrics/benchmark-embedders
# =============================================================
@router.post(
    "/benchmark-embedders",
    response_model=EmbeddingBenchmarkResponse,
    status_code=status.HTTP_200_OK,
    summary="Benchmark de provedores de embedding",
    description=(
        "Vetoriza a `query` em todos os providers disponíveis no ambiente "
        "(sentence_transformers sempre; openai se `OPENAI_API_KEY` estiver "
        "configurada). Retorna latência real e custo estimado por provider.\\n\\n"
        "Útil para decidir qual provider usar no corpus antes do upload."
    ),
    responses={
        200: {"description": "Benchmark executado."},
        401: {"description": "Token ausente ou inválido."},
        422: {"description": "Query muito curta (mínimo 3 caracteres)."},
    },
)
def benchmark_embedders(
    payload: EmbeddingBenchmarkRequest,
    token_payload: CurrentTokenDependency,
    benchmark_use_case: EmbeddingBenchmarkUseCaseDependency,
) -> EmbeddingBenchmarkResponse:
    result = benchmark_use_case.run(
        query=payload.query,
        owner_id=token_payload.user_id,
    )

    return EmbeddingBenchmarkResponse(
        query=result.query,
        results=[
            EmbeddingProviderBenchmarkItem(
                provider_name=r.provider_name,
                model_name=r.model_name,
                dimensions=r.dimensions,
                latency_ms=r.latency_ms,
                cost_usd_per_million_tokens=r.cost_usd_per_million_tokens,
                vector_size_bytes=r.vector_size_bytes,
            )
            for r in result.results
        ],
        fastest_provider=result.fastest_provider,
        cheapest_provider=result.cheapest_provider,
    )


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _serialize_storage_savings(
    savings: StorageSavings | None,
) -> StorageSavingsResponse | None:
    if savings is None:
        return None
    return StorageSavingsResponse(
        total_chunks=savings.total_chunks,
        original_dim=savings.original_dim,
        best_compressed_dim=savings.best_compressed_dim,
        best_method=savings.best_method,
        original_storage_mb=savings.original_storage_mb,
        compressed_storage_mb=savings.compressed_storage_mb,
        savings_pct=savings.savings_pct,
        pinecone_original_usd=savings.pinecone_original_usd,
        pinecone_compressed_usd=savings.pinecone_compressed_usd,
        qdrant_original_usd=savings.qdrant_original_usd,
        qdrant_compressed_usd=savings.qdrant_compressed_usd,
        pinecone_savings_brl=savings.pinecone_savings_brl,
        qdrant_savings_brl=savings.qdrant_savings_brl,
    )
