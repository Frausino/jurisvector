"""Testes unit do AnswerUseCase com fakes em memória.

Refletem o contrato pós-Bloco 5:
- `AnswerUseCase.__init__` recebe apenas retrieval + audit.
- `ask(ask_input, llm_client=...)` recebe o cliente LLM explícito.
- `AskInput.llm_provider` é obrigatório (metadado de auditoria).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from docuvector.application.answer_use_case import AnswerUseCase, AskInput
from docuvector.application.retrieval_use_case import RetrievalUseCase
from docuvector.domain.entities import AuditEvent, RetrievedChunk
from docuvector.domain.enums import (
    AuditAction,
    AuditStatus,
    EmbeddingProviderName,
    LlmProviderName,
)
from docuvector.domain.exceptions import LlmGenerationError
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector
from docuvector.domain.interfaces.llm_client import LlmCompletion


# =============================================================
# Fakes
# =============================================================
class _FakeEmbedder:
    @property
    def provider_name(self) -> EmbeddingProviderName:
        return EmbeddingProviderName.SENTENCE_TRANSFORMERS

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimensions(self) -> int:
        return 4

    def embed_query(self, _text: str) -> EmbeddingVector:
        return (0.1, 0.2, 0.3, 0.4)

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        return [(0.1, 0.2, 0.3, 0.4) for _ in texts]


class _StaticVectorStore:
    def __init__(self, chunks_to_return: Sequence[RetrievedChunk]) -> None:
        self._chunks_to_return = chunks_to_return

    def add_chunks(self, _chunks) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def search(self, *_args, **_kwargs) -> Sequence[RetrievedChunk]:  # type: ignore[no-untyped-def]
        return self._chunks_to_return

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        return np.empty((0, 0), dtype=np.float32)

    def delete_document(self, _owner_id: UUID, _document_id: UUID) -> int:
        raise NotImplementedError


class _StubLlmClient:
    """LLM fake configurável: devolve texto fixo OU levanta erro."""

    def __init__(
        self,
        response_text: str = "Resposta com fonte [1].",
        tokens_used: int = 100,
        cost_usd: float = 0.0005,
        latency_ms: int = 250,
        should_fail: bool = False,
        model_name: str = "gpt-4o-mini",
    ) -> None:
        self._response_text = response_text
        self._tokens_used = tokens_used
        self._cost_usd = cost_usd
        self._latency_ms = latency_ms
        self._should_fail = should_fail
        self._model_name = model_name
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None

    def complete(self, system_prompt: str, user_prompt: str) -> LlmCompletion:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if self._should_fail:
            raise LlmGenerationError("simulated LLM upstream failure")
        return LlmCompletion(
            text=self._response_text,
            tokens_used=self._tokens_used,
            cost_usd=self._cost_usd,
            latency_ms=self._latency_ms,
            model=self._model_name,
        )


class _InMemoryAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        raise NotImplementedError


def _make_chunk(text: str = "cláusula de rescisão") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_filename="contrato.pdf",
        text=text,
        similarity=0.92,
        chunk_index=0,
    )


def _build_use_case(
    chunks_to_return: Sequence[RetrievedChunk],
    audit_repository: _InMemoryAuditRepository,
) -> AnswerUseCase:
    retrieval = RetrievalUseCase(
        vector_store=_StaticVectorStore(chunks_to_return),
        default_top_k=5,
        default_similarity_threshold=0.6,
    )
    return AnswerUseCase(
        retrieval_use_case=retrieval,
        audit_repository=audit_repository,
    )


def _make_ask_input(
    query: str = "pergunta padrão",
    llm_provider: LlmProviderName = LlmProviderName.MOCK,
    client_ip: str | None = None,
    user_agent: str | None = None,
    owner_id: UUID | None = None,
) -> AskInput:
    return AskInput(
        owner_id=owner_id if owner_id is not None else uuid4(),
        query=query,
        embedding_provider=_FakeEmbedder(),
        llm_provider=llm_provider,
        client_ip=client_ip,
        user_agent=user_agent,
    )


# =============================================================
# Fluxo feliz
# =============================================================
@pytest.mark.unit
def test_ask_returns_answer_with_sources_when_context_available() -> None:
    chunk = _make_chunk()
    llm = _StubLlmClient(response_text="A cláusula está em [1].")
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([chunk], audit)

    answer = use_case.ask(
        _make_ask_input(query="Qual a cláusula de rescisão?"),
        llm_client=llm,
    )

    assert answer.text == "A cláusula está em [1]."
    assert answer.sources == (chunk,)
    assert answer.grounded is True
    assert answer.tokens_used == 100
    assert answer.cost_usd == pytest.approx(0.0005)
    assert answer.model == "gpt-4o-mini"


@pytest.mark.unit
def test_ask_passes_numbered_context_to_llm() -> None:
    chunk = _make_chunk(text="conteudo do trecho 1")
    llm = _StubLlmClient()
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([chunk], audit)

    use_case.ask(_make_ask_input(), llm_client=llm)

    assert llm.last_user_prompt is not None
    assert "[1]" in llm.last_user_prompt
    assert "conteudo do trecho 1" in llm.last_user_prompt
    assert "contrato.pdf" in llm.last_user_prompt


# =============================================================
# Detecção de grounded
# =============================================================
@pytest.mark.unit
def test_ask_marks_not_grounded_when_no_chunks_retrieved() -> None:
    """Sem chunks, grounded é False mesmo que o LLM gere algo."""
    llm = _StubLlmClient(response_text="Resposta inventada")
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([], audit)

    answer = use_case.ask(
        _make_ask_input(query="pergunta sem contexto"),
        llm_client=llm,
    )

    assert answer.grounded is False
    assert answer.sources == ()


@pytest.mark.unit
def test_ask_marks_not_grounded_when_llm_abstains() -> None:
    """LLM diz a frase canônica de abstenção → grounded=False."""
    abstention_text = (
        "Não tenho contexto suficiente nos documentos fornecidos para "
        "responder a essa pergunta com segurança."
    )
    chunk = _make_chunk()
    llm = _StubLlmClient(response_text=abstention_text)
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([chunk], audit)

    answer = use_case.ask(
        _make_ask_input(query="pergunta tangencial"),
        llm_client=llm,
    )

    assert answer.grounded is False


@pytest.mark.unit
def test_ask_marks_not_grounded_for_abstention_with_different_case() -> None:
    """Detecção é case-insensitive."""
    abstention_text = "NÃO TENHO CONTEXTO SUFICIENTE para isso."
    chunk = _make_chunk()
    llm = _StubLlmClient(response_text=abstention_text)
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([chunk], audit)

    answer = use_case.ask(_make_ask_input(), llm_client=llm)

    assert answer.grounded is False


# =============================================================
# Audit log
# =============================================================
@pytest.mark.unit
def test_ask_emits_success_audit_with_metrics_and_llm_provider() -> None:
    chunk = _make_chunk()
    llm = _StubLlmClient(tokens_used=123, cost_usd=0.0008)
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([chunk], audit)
    owner_id = uuid4()

    use_case.ask(
        _make_ask_input(
            query="pergunta auditada",
            llm_provider=LlmProviderName.OLLAMA,
            client_ip="127.0.0.1",
            user_agent="pytest",
            owner_id=owner_id,
        ),
        llm_client=llm,
    )

    success_events = [
        event
        for event in audit.events
        if event.action is AuditAction.QUERY_EXECUTED and event.status is AuditStatus.SUCCESS
    ]
    assert len(success_events) == 1
    event = success_events[0]
    assert event.actor_user_id == owner_id
    assert event.metadata is not None
    assert event.metadata["tokens_used"] == 123
    assert event.metadata["cost_usd"] == pytest.approx(0.0008)
    assert event.metadata["sources_count"] == 1
    assert event.metadata["grounded"] is True
    assert event.metadata["embedding_provider"] == EmbeddingProviderName.SENTENCE_TRANSFORMERS.value
    assert event.metadata["llm_provider"] == LlmProviderName.OLLAMA.value


@pytest.mark.unit
def test_ask_emits_failure_audit_when_llm_breaks() -> None:
    chunk = _make_chunk()
    llm = _StubLlmClient(should_fail=True)
    audit = _InMemoryAuditRepository()
    use_case = _build_use_case([chunk], audit)

    with pytest.raises(LlmGenerationError):
        use_case.ask(
            _make_ask_input(
                query="pergunta que vai falhar",
                llm_provider=LlmProviderName.OPENAI,
            ),
            llm_client=llm,
        )

    failure_events = [
        event
        for event in audit.events
        if event.action is AuditAction.QUERY_EXECUTED and event.status is AuditStatus.FAILURE
    ]
    assert len(failure_events) == 1
    assert failure_events[0].metadata is not None
    assert failure_events[0].metadata["reason"] == "llm_failure"
    assert failure_events[0].metadata["llm_provider"] == LlmProviderName.OPENAI.value
