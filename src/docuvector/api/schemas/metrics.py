"""Schemas Pydantic para os endpoints da Sprint 4B.

- EmbeddingBenchmark: comparação de latência/custo entre providers.
- MetricsDashboard: KPIs agregados do audit_log e documentos.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from docuvector.domain.enums import EmbeddingProviderName


# ---------------------------------------------------------------
# Embedding Benchmark
# ---------------------------------------------------------------
class EmbeddingBenchmarkRequest(BaseModel):
    """Texto a vetorizar para o benchmark."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        min_length=3,
        max_length=500,
        description="Texto de consulta a ser vetorizado pelos providers.",
    )


class EmbeddingProviderBenchmarkItem(BaseModel):
    """Resultado de um provider no benchmark de embedding."""

    model_config = ConfigDict(frozen=True)

    provider_name: EmbeddingProviderName
    model_name: str
    dimensions: int = Field(ge=1)
    latency_ms: int = Field(ge=0)
    cost_usd_per_million_tokens: float = Field(
        ge=0.0,
        description="Custo em USD por 1 milhão de tokens de embedding.",
    )
    vector_size_bytes: int = Field(ge=0)


class EmbeddingBenchmarkResponse(BaseModel):
    """Comparação completa entre os providers de embedding disponíveis."""

    model_config = ConfigDict(frozen=True)

    query: str
    results: list[EmbeddingProviderBenchmarkItem]
    fastest_provider: EmbeddingProviderName
    cheapest_provider: EmbeddingProviderName


# ---------------------------------------------------------------
# Dashboard de métricas
# ---------------------------------------------------------------
class LlmProviderStatsResponse(BaseModel):
    """KPIs de um provider LLM."""

    model_config = ConfigDict(frozen=True)

    provider: str
    total_calls: int = Field(ge=0)
    avg_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    total_tokens: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0)


class CompressionStatsResponse(BaseModel):
    """KPIs de um método de compressão."""

    model_config = ConfigDict(frozen=True)

    method: str
    avg_semantic_retention: float = Field(ge=0.0, le=1.0)
    avg_space_savings_pct: float


class DocumentStatsResponse(BaseModel):
    """Contagem de documentos por status."""

    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=0)
    embedded: int = Field(ge=0)
    failed: int = Field(ge=0)
    processing: int = Field(ge=0)


class StorageSavingsResponse(BaseModel):
    """Economia de armazenamento e estimativas de custo em provedores externos.

    Os campos `*_usd` e `*_brl` são estimativas baseadas em preços
    públicos de mai/2026. A taxa de câmbio é configurável via
    `USD_TO_BRL_RATE` no `.env`.
    """

    model_config = ConfigDict(frozen=True)

    total_chunks: int = Field(ge=0)
    original_dim: int = Field(ge=1)
    best_compressed_dim: int = Field(ge=1)
    best_method: str
    original_storage_mb: float = Field(ge=0.0)
    compressed_storage_mb: float = Field(ge=0.0)
    savings_pct: float
    pinecone_original_usd: float = Field(ge=0.0)
    pinecone_compressed_usd: float = Field(ge=0.0)
    qdrant_original_usd: float = Field(ge=0.0)
    qdrant_compressed_usd: float = Field(ge=0.0)
    pinecone_savings_brl: float
    qdrant_savings_brl: float


class DashboardResponse(BaseModel):
    """KPIs consolidados do dashboard operacional."""

    model_config = ConfigDict(frozen=True)

    llm_stats: list[LlmProviderStatsResponse]
    compression_stats: list[CompressionStatsResponse]
    document_stats: DocumentStatsResponse
    storage_savings: StorageSavingsResponse | None = Field(
        default=None,
        description="None quando nenhum benchmark de compressão foi executado.",
    )
    total_queries: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0)
    total_cost_brl: float = Field(ge=0.0)
