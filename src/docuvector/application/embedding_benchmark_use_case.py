"""Caso de uso: benchmark de provedores de embedding.

Compara latência de vetorização e custo estimado entre os provedores
disponíveis no ambiente (sentence_transformers e/ou openai).

Diferente do benchmark de compressão, este use case **não persiste**
nada no banco: é consulta ad-hoc para apoiar a decisão de qual
provider usar num corpus. O resultado é retornado diretamente ao
cliente e registrado no audit log para rastreabilidade.

Decisões de design:

1. Sem chamada de rede para sentence-transformers (local).
   Para OpenAI, uma chamada real é feita com a query fornecida.
   Isso é intencional: latência real é mais valiosa que estimativa.

2. Custo OpenAI estimado via `openai_embedding_cost_per_million_tokens`
   do Settings. Sentence-transformers tem custo 0.0.

3. Sem persistência. O resultado é efêmero: é uma ferramenta de
   análise, não parte do pipeline de ingestão.

4. Falha isolada por provider. Se OpenAI não estiver configurado,
   retorna só sentence-transformers sem abortar.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from dataclasses import dataclass
from uuid import UUID

from docuvector.config.settings import Settings
from docuvector.domain.entities import AuditEvent
from docuvector.domain.enums import AuditAction, AuditStatus, EmbeddingProviderName
from docuvector.domain.exceptions import EmbeddingGenerationError
from docuvector.domain.interfaces import AuditRepository
from docuvector.domain.interfaces.embedding_provider import EmbeddingProvider
from docuvector.infrastructure.embeddings.factory import (
    list_available_providers,
    resolve_embedder,
)

logger = logging.getLogger(__name__)

_BYTES_PER_FLOAT32: float = 4.0
_PROVIDER_TIMEOUT_SECONDS: float = 60.0  # timeout por provider no benchmark
_RESOURCE_TYPE: str = "embedding_benchmark"


@dataclass(frozen=True, slots=True)
class EmbeddingProviderResult:
    """Resultado de um provider individual no benchmark."""

    provider_name: EmbeddingProviderName
    model_name: str
    dimensions: int
    latency_ms: int
    cost_usd_per_million_tokens: float
    # Custo sempre em USD/milhão de tokens para consistência.
    # sentence-transformers: 0.0 (local). OpenAI: derivado do Settings.
    vector_size_bytes: int  # bytes de um único vetor float32


@dataclass(frozen=True, slots=True)
class EmbeddingBenchmarkResult:
    """Resultado completo do benchmark de provedores de embedding."""

    query: str
    results: tuple[EmbeddingProviderResult, ...]
    fastest_provider: EmbeddingProviderName
    cheapest_provider: EmbeddingProviderName


class EmbeddingBenchmarkUseCase:
    """Compara latência e custo entre os provedores de embedding disponíveis."""

    def __init__(
        self,
        audit_repository: AuditRepository,
        settings: Settings,
    ) -> None:
        self._audit = audit_repository
        self._settings = settings

    def run(self, query: str, owner_id: UUID) -> EmbeddingBenchmarkResult:
        """Executa o benchmark e retorna a comparação.

        Args:
            query: Texto de consulta a ser vetorizado.
            owner_id: UUID do usuário (para audit log).

        Returns:
            EmbeddingBenchmarkResult com todos os providers testados.
        """
        available_providers = list_available_providers(self._settings)

        results: list[EmbeddingProviderResult] = []
        for provider_name in available_providers:
            try:
                result = self._benchmark_provider(
                    provider_name=provider_name,
                    query=query,
                )
                results.append(result)
            except Exception as provider_failure:
                logger.warning(
                    "Benchmark de embedding falhou para %s: %s",
                    provider_name.value,
                    provider_failure,
                    exc_info=True,
                )

        if not results:
            raise EmbeddingGenerationError(
                "Nenhum provider de embedding produziu resultado. "
                "Verifique se sentence-transformers está instalado."
            )

        fastest = min(results, key=lambda r: r.latency_ms)
        cheapest = min(results, key=lambda r: r.cost_usd_per_million_tokens)

        benchmark_result = EmbeddingBenchmarkResult(
            query=query,
            results=tuple(results),
            fastest_provider=fastest.provider_name,
            cheapest_provider=cheapest.provider_name,
        )
        self._emit_audit(owner_id=owner_id, result=benchmark_result)
        return benchmark_result

    def _benchmark_provider(
        self,
        provider_name: EmbeddingProviderName,
        query: str,
    ) -> EmbeddingProviderResult:
        embedder: EmbeddingProvider = resolve_embedder(provider_name)

        start = time.perf_counter()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(embedder.embed_query, query)
                future.result(timeout=_PROVIDER_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError as timeout_error:
            raise EmbeddingGenerationError(
                f"Provider {provider_name.value} excedeu o timeout de {_PROVIDER_TIMEOUT_SECONDS}s."
            ) from timeout_error
        latency_ms = int((time.perf_counter() - start) * 1000)

        cost = self._estimate_cost_per_million_tokens(provider_name)
        vector_size = int(embedder.dimensions * _BYTES_PER_FLOAT32)

        return EmbeddingProviderResult(
            provider_name=provider_name,
            model_name=embedder.model_name,
            dimensions=embedder.dimensions,
            latency_ms=latency_ms,
            cost_usd_per_million_tokens=cost,
            vector_size_bytes=vector_size,
        )

    def _emit_audit(
        self,
        owner_id: UUID,
        result: EmbeddingBenchmarkResult,
    ) -> None:
        """Registra o benchmark no ledger de auditoria.

        Permite rastrear histórico de latência e custo por provider
        ao longo do tempo, alimentando o dashboard da Sprint 4B.
        """
        self._audit.append(
            AuditEvent(
                actor_user_id=owner_id,
                action=AuditAction.QUERY_EXECUTED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                metadata={
                    "benchmark_type": "embedding",
                    "providers_tested": [r.provider_name.value for r in result.results],
                    "fastest_provider": result.fastest_provider.value,
                    "cheapest_provider": result.cheapest_provider.value,
                    "latencies_ms": {r.provider_name.value: r.latency_ms for r in result.results},
                    "costs_usd_per_million_tokens": {
                        r.provider_name.value: r.cost_usd_per_million_tokens for r in result.results
                    },
                },
            )
        )

    def _estimate_cost_per_million_tokens(
        self,
        provider_name: EmbeddingProviderName,
    ) -> float:
        """Custo em USD por 1 milhão de tokens de embedding.

        Sentence-transformers: 0.0 (local, sem custo monetário).
        OpenAI: lido diretamente de Settings para ser configurável
        sem redeploy e testável via injeção.
        """
        if provider_name is EmbeddingProviderName.SENTENCE_TRANSFORMERS:
            return 0.0
        return self._settings.openai_embedding_cost_per_million_tokens
