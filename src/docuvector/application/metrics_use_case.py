"""Caso de uso: agregação de KPIs operacionais.

Lê `audit_logs.metadata` (JSONB no Postgres) e `documents` para
produzir os indicadores do dashboard da Sprint 4B.

Decisões de design:

1. **SQL via SQLAlchemy Core (text), não ORM**.
   Consultas de agregação com operadores JSONB são verbosas em ORM.
   `text()` com parâmetros vinculados é mais legível e igualmente
   seguro contra SQL injection (nenhum valor vem direto do usuário
   sem binding).

2. **Sem cache em memória**. O resultado reflete o estado atual do
   banco. Cache pode ser adicionado na Sprint 5 com `functools.lru_cache`
   + TTL se o dashboard ficar lento.

3. **Estimativa de custo em R$**. Taxa de câmbio hardcoded em
   `Settings.usd_to_brl_rate` (default 5.70). Operadores podem
   atualizar via variável de ambiente sem redeploy.

4. **Pinecone/Qdrant pricing** hardcoded em constantes nomeadas.
   Modelos de preço mudam raramente; a tabela versionada no
   repositório é auditável.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from docuvector.config.settings import get_settings
from docuvector.domain.enums import CompressionMethod

# ---------------------------------------------------------------
# Pricing de provedores de vetor (USD por 1M de vetores/mês)
# Fonte: páginas de pricing de mai/2026 — atualizar em Settings futuramente
# ---------------------------------------------------------------
# TODO(sprint5b): mover pricing para Settings ou tabela versionada no banco.
# Preços de mai/2026 — atualizar conforme pricing page dos provedores.
_PINECONE_USD_PER_MILLION_VECTORS_MONTH: float = 0.033  # Serverless write
_QDRANT_USD_PER_GB_MONTH: float = 0.025  # Cloud managed
_BYTES_PER_FLOAT32: int = 4
_BYTES_PER_MB: float = 1024.0 * 1024.0  # mantém float para divisão
_BYTES_PER_GB: float = 1024.0 * 1024.0 * 1024.0


@dataclass(frozen=True, slots=True)
class LlmProviderStats:
    """KPIs de geração de resposta por provider LLM."""

    provider: str
    total_calls: int
    avg_latency_ms: float
    p95_latency_ms: float
    total_tokens: int
    total_cost_usd: float


@dataclass(frozen=True, slots=True)
class CompressionStats:
    """KPIs de compressão por método."""

    method: str
    avg_semantic_retention: float
    avg_space_savings_pct: float


@dataclass(frozen=True, slots=True)
class StorageSavings:
    """Estimativa de economia de armazenamento e custo em provedores externos."""

    total_chunks: int
    original_dim: int
    best_compressed_dim: int
    best_method: str
    original_storage_mb: float
    compressed_storage_mb: float
    savings_pct: float
    # Estimativas mensais
    pinecone_original_usd: float
    pinecone_compressed_usd: float
    qdrant_original_usd: float
    qdrant_compressed_usd: float
    # Em R$ (taxa de câmbio configurável)
    pinecone_savings_brl: float
    qdrant_savings_brl: float


@dataclass(frozen=True, slots=True)
class DocumentStats:
    """Contagem de documentos por status."""

    total: int
    embedded: int
    failed: int
    processing: int


@dataclass(frozen=True, slots=True)
class DashboardMetrics:
    """Todos os KPIs do dashboard em um único objeto."""

    llm_stats: tuple[LlmProviderStats, ...]
    compression_stats: tuple[CompressionStats, ...]
    document_stats: DocumentStats
    storage_savings: StorageSavings | None  # None se não houver benchmark rodado
    total_queries: int
    total_cost_usd: float
    total_cost_brl: float


# ---------------------------------------------------------------
# Chaves de schema do audit_logs.metadata.
# Centralizar aqui evita drift silencioso: se uma chave mudar em
# CompressionBenchmarkUseCase ou AnswerUseCase, quebra neste arquivo
# em vez de no dashboard em produção.
# TODO(sprint5b): migrar para EventMetadata versionado.
# ---------------------------------------------------------------
_AUDIT_KEY_LLM_PROVIDER: str = "llm_provider"
_AUDIT_KEY_LATENCY_MS: str = "latency_ms"
_AUDIT_KEY_TOKENS_USED: str = "tokens_used"
_AUDIT_KEY_COST_USD: str = "cost_usd"
_AUDIT_KEY_BENCHMARK_TYPE: str = "benchmark_type"
_AUDIT_KEY_BEST_METHOD: str = "best_method"
_AUDIT_KEY_BEST_RETENTION: str = "best_retention"
_AUDIT_KEY_BEST_SAVINGS_PCT: str = "best_space_savings_pct"
_AUDIT_VALUE_BENCHMARK_COMPRESSION: str = "compression"


class MetricsUseCase:
    """Agrega KPIs do audit_log e documentos para o dashboard."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_dashboard(self, owner_id: UUID) -> DashboardMetrics:
        """Calcula todos os KPIs para o dashboard do usuário.

        Args:
            owner_id: Filtra métricas pelo dono. Isolamento multi-tenant.
        """
        with self._session_factory() as session:
            llm_stats = self._query_llm_stats(session, owner_id)
            compression_stats = self._query_compression_stats(session, owner_id)
            document_stats = self._query_document_stats(session, owner_id)
            storage_savings = self._calculate_storage_savings(session, owner_id)

        total_queries = sum(s.total_calls for s in llm_stats)
        total_cost_usd = sum(s.total_cost_usd for s in llm_stats)
        settings = get_settings()
        usd_to_brl = settings.usd_to_brl_rate

        return DashboardMetrics(
            llm_stats=tuple(llm_stats),
            compression_stats=tuple(compression_stats),
            document_stats=document_stats,
            storage_savings=storage_savings,
            total_queries=total_queries,
            total_cost_usd=total_cost_usd,
            total_cost_brl=round(total_cost_usd * usd_to_brl, 2),
        )

    # ---------------------------------------------------------------
    # Queries SQL
    # ---------------------------------------------------------------
    def _query_llm_stats(self, session: Session, owner_id: UUID) -> list[LlmProviderStats]:
        """Agrega latência e custo por provider LLM."""
        sql = text("""
            SELECT
                metadata->>'llm_provider'          AS provider,
                COUNT(*)                                   AS total_calls,
                AVG((metadata->>'latency_ms')::int)  AS avg_latency_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY (metadata->>'latency_ms')::int
                )                                          AS p95_latency_ms,
                SUM((metadata->>'tokens_used')::int) AS total_tokens,
                SUM((metadata->>'cost_usd')::float)  AS total_cost_usd
            FROM audit_logs
            WHERE action = 'query_executed'
              AND status = 'success'
              AND actor_user_id = :owner_id
              AND metadata->>'llm_provider' IS NOT NULL
            GROUP BY metadata->>'llm_provider'
            ORDER BY total_calls DESC
        """)
        rows = session.execute(sql, {"owner_id": str(owner_id)}).fetchall()
        return [
            LlmProviderStats(
                provider=str(row.provider),
                total_calls=int(row.total_calls),
                avg_latency_ms=float(row.avg_latency_ms or 0),
                p95_latency_ms=float(row.p95_latency_ms or 0),
                total_tokens=int(row.total_tokens or 0),
                total_cost_usd=float(row.total_cost_usd or 0),
            )
            for row in rows
        ]

    def _query_compression_stats(self, session: Session, owner_id: UUID) -> list[CompressionStats]:
        """Agrega retenção semântica e economia por método de compressão."""
        sql = text("""
            SELECT
                metadata->>'best_method'                         AS method,
                AVG((metadata->>'best_retention')::float)        AS avg_retention,
                AVG((metadata->>'best_space_savings_pct')::float) AS avg_savings
            FROM audit_logs
            WHERE action = 'document_updated'
              AND status = 'success'
              AND actor_user_id = :owner_id
              AND metadata->>'benchmark_type' = 'compression'
            GROUP BY metadata->>'best_method'
            ORDER BY avg_retention DESC
        """)
        rows = session.execute(sql, {"owner_id": str(owner_id)}).fetchall()
        return [
            CompressionStats(
                method=str(row.method),
                avg_semantic_retention=float(row.avg_retention or 0),
                avg_space_savings_pct=float(row.avg_savings or 0),
            )
            for row in rows
        ]

    def _query_document_stats(self, session: Session, owner_id: UUID) -> DocumentStats:
        """Contagem de documentos por status."""
        sql = text("""
            SELECT
                COUNT(*)                                          AS total,
                COUNT(*) FILTER (WHERE status = 'embedded')      AS embedded,
                COUNT(*) FILTER (WHERE status = 'failed')        AS failed,
                COUNT(*) FILTER (
                    WHERE status IN ('uploaded','extracting',
                                     'extracted','chunking',
                                     'chunked','embedding')
                )                                                  AS processing
            FROM documents
            WHERE owner_id = :owner_id
        """)
        row = session.execute(sql, {"owner_id": str(owner_id)}).fetchone()
        if row is None:
            return DocumentStats(total=0, embedded=0, failed=0, processing=0)
        return DocumentStats(
            total=int(row.total or 0),
            embedded=int(row.embedded or 0),
            failed=int(row.failed or 0),
            processing=int(row.processing or 0),
        )

    def _calculate_storage_savings(self, session: Session, owner_id: UUID) -> StorageSavings | None:
        """Calcula economia de armazenamento com base no melhor compressor."""
        sql = text("""
            SELECT
                COUNT(dc.id)          AS total_chunks,
                d.original_dimension  AS original_dim,
                d.compressed_dimension AS compressed_dim,
                d.compression_method  AS method
            FROM documents d
            JOIN document_chunks dc ON dc.document_id = d.id
            WHERE d.owner_id = :owner_id
              AND d.compression_method IS NOT NULL
              AND d.original_dimension IS NOT NULL
              AND d.compressed_dimension IS NOT NULL
            GROUP BY d.original_dimension, d.compressed_dimension, d.compression_method
            ORDER BY COUNT(dc.id) DESC
            LIMIT 1
        """)
        row = session.execute(sql, {"owner_id": str(owner_id)}).fetchone()
        if row is None:
            return None

        total_chunks = int(row.total_chunks)
        original_dim = int(row.original_dim)
        compressed_dim = int(row.compressed_dim)
        method = str(row.method)

        # bytes_per_element depende do método
        bytes_per_element = _bytes_per_element_for_method(method)

        original_bytes = total_chunks * original_dim * _BYTES_PER_FLOAT32
        compressed_bytes = total_chunks * compressed_dim * bytes_per_element

        original_mb = original_bytes / _BYTES_PER_MB
        compressed_mb = compressed_bytes / _BYTES_PER_MB
        savings_pct = (
            (1.0 - compressed_bytes / original_bytes) * 100.0 if original_bytes > 0 else 0.0
        )

        settings = get_settings()
        usd_brl = settings.usd_to_brl_rate

        # Pinecone: cobrança por vetor armazenado/mês
        pinecone_orig = (total_chunks / 1_000_000) * _PINECONE_USD_PER_MILLION_VECTORS_MONTH
        pinecone_comp = pinecone_orig  # Pinecone cobra por vetor, não por dimensão

        # Qdrant: cobrança por GB armazenado/mês
        qdrant_orig = (original_bytes / _BYTES_PER_GB) * _QDRANT_USD_PER_GB_MONTH
        qdrant_comp = (compressed_bytes / _BYTES_PER_GB) * _QDRANT_USD_PER_GB_MONTH

        return StorageSavings(
            total_chunks=total_chunks,
            original_dim=original_dim,
            best_compressed_dim=compressed_dim,
            best_method=method,
            original_storage_mb=round(original_mb, 4),
            compressed_storage_mb=round(compressed_mb, 4),
            savings_pct=round(savings_pct, 2),
            pinecone_original_usd=round(pinecone_orig, 4),
            pinecone_compressed_usd=round(pinecone_comp, 4),
            qdrant_original_usd=round(qdrant_orig, 4),
            qdrant_compressed_usd=round(qdrant_comp, 4),
            pinecone_savings_brl=round((pinecone_orig - pinecone_comp) * usd_brl, 2),
            qdrant_savings_brl=round((qdrant_orig - qdrant_comp) * usd_brl, 2),
        )


def _bytes_per_element_for_method(method: str) -> float:
    """Devolve bytes por elemento para o método de compressão."""
    mapping: dict[str, float] = {
        CompressionMethod.PCA.value: 4.0,
        CompressionMethod.RANDOM_PROJECTION.value: 4.0,
        CompressionMethod.INT8.value: 1.0,
        CompressionMethod.BINARY.value: 0.125,
    }
    return mapping.get(method, 4.0)
