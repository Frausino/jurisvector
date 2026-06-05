"""Testes unit da Sprint 4B — EmbeddingBenchmarkUseCase e MetricsUseCase."""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest

from docuvector.application.embedding_benchmark_use_case import (
    EmbeddingBenchmarkUseCase,
)
from docuvector.application.metrics_use_case import (
    _bytes_per_element_for_method,
)
from docuvector.config.settings import get_settings
from docuvector.domain.entities import AuditEvent
from docuvector.domain.enums import EmbeddingProviderName
from docuvector.domain.exceptions import EmbeddingGenerationError


# ---------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------
class _FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        return []


# ---------------------------------------------------------------
# Testes de _bytes_per_element_for_method (função pura)
# ---------------------------------------------------------------
_FLOAT32_BYTES = 4.0
_INT8_BYTES = 1.0
_BINARY_BYTES = 0.125


@pytest.mark.unit
class TestBytesPerElementForMethod:
    def test_pca_retorna_float32(self) -> None:
        assert _bytes_per_element_for_method("pca") == _FLOAT32_BYTES

    def test_random_projection_retorna_float32(self) -> None:
        assert _bytes_per_element_for_method("random_projection") == _FLOAT32_BYTES

    def test_int8_retorna_1_byte(self) -> None:
        assert _bytes_per_element_for_method("int8") == _INT8_BYTES

    def test_binary_retorna_0_125_bytes(self) -> None:
        assert _bytes_per_element_for_method("binary") == _BINARY_BYTES

    def test_metodo_desconhecido_retorna_float32(self) -> None:
        """Fallback seguro: método desconhecido assume float32."""
        assert _bytes_per_element_for_method("unknown") == _FLOAT32_BYTES


# ---------------------------------------------------------------
# Testes do EmbeddingBenchmarkUseCase
# ---------------------------------------------------------------
@pytest.mark.unit
class TestEmbeddingBenchmarkUseCase:
    def test_custo_sentence_transformers_e_zero(self) -> None:
        settings = get_settings()
        uc = EmbeddingBenchmarkUseCase(
            audit_repository=_FakeAuditRepository(),
            settings=settings,
        )
        cost = uc._estimate_cost_per_million_tokens(EmbeddingProviderName.SENTENCE_TRANSFORMERS)
        assert cost == 0.0

    def test_custo_openai_e_positivo(self) -> None:
        settings = get_settings()
        uc = EmbeddingBenchmarkUseCase(
            audit_repository=_FakeAuditRepository(),
            settings=settings,
        )
        cost = uc._estimate_cost_per_million_tokens(EmbeddingProviderName.OPENAI)
        assert cost > 0.0

    def test_sentence_transformers_mais_barato_que_openai(self) -> None:
        settings = get_settings()
        uc = EmbeddingBenchmarkUseCase(
            audit_repository=_FakeAuditRepository(),
            settings=settings,
        )
        cost_st = uc._estimate_cost_per_million_tokens(EmbeddingProviderName.SENTENCE_TRANSFORMERS)
        cost_oai = uc._estimate_cost_per_million_tokens(EmbeddingProviderName.OPENAI)
        assert cost_st < cost_oai


# ---------------------------------------------------------------
# Testes do audit emit
# ---------------------------------------------------------------
@pytest.mark.unit
class TestEmbeddingBenchmarkAudit:
    def _make_use_case(self) -> tuple[EmbeddingBenchmarkUseCase, _FakeAuditRepository]:
        audit = _FakeAuditRepository()
        uc = EmbeddingBenchmarkUseCase(
            audit_repository=audit,
            settings=get_settings(),
        )
        return uc, audit

    def test_audit_e_registrado_apos_benchmark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """run() deve emitir exatamente 1 evento no audit log."""

        def _fake_embed(
            self: object,
            text: str,
        ) -> tuple[float, ...]:
            return tuple(float(x) for x in np.zeros(384))

        monkeypatch.setattr(
            "docuvector.infrastructure.embeddings."
            "sentence_transformers_embedder.SentenceTransformersEmbedder.embed_query",
            _fake_embed,
        )

        uc, audit = self._make_use_case()
        uc.run(query="contrato de prestacao de servicos", owner_id=uuid4())

        assert len(audit.events) == 1
        event = audit.events[0]
        assert event.metadata["benchmark_type"] == "embedding"
        assert "fastest_provider" in event.metadata
        assert "latencies_ms" in event.metadata

    def test_audit_nao_registrado_se_sem_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Se nenhum provider funcionar, não deve emitir audit (exceção antes)."""

        def _fail(
            self: object,
            text: str,
        ) -> tuple[float, ...]:
            raise RuntimeError("provider indisponível")

        monkeypatch.setattr(
            "docuvector.infrastructure.embeddings."
            "sentence_transformers_embedder.SentenceTransformersEmbedder.embed_query",
            _fail,
        )

        uc, audit = self._make_use_case()

        with pytest.raises(EmbeddingGenerationError):
            uc.run(query="contrato de servicos juridicos", owner_id=uuid4())

        assert len(audit.events) == 0
