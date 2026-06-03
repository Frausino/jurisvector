"""Testes unit do MockLlmClient."""

from __future__ import annotations

import pytest

from docuvector.infrastructure.llm.mock_llm_client import MockLlmClient


@pytest.mark.unit
def test_mock_returns_canonical_answer_when_prompt_has_context() -> None:
    client = MockLlmClient()

    completion = client.complete(
        system_prompt="qualquer system prompt",
        user_prompt=(
            "Trechos de documentos disponíveis para consulta:\n\n"
            "[1] Documento: foo.pdf\nconteudo\n\n---\n\nPergunta: ?"
        ),
    )

    assert "[1]" in completion.text
    assert "[MOCK]" in completion.text


@pytest.mark.unit
def test_mock_returns_canonical_abstention_when_prompt_has_no_context() -> None:
    """Sem contexto → frase canônica que o AnswerUseCase detecta como grounded=False."""
    client = MockLlmClient()

    completion = client.complete(
        system_prompt="qualquer",
        user_prompt=(
            "Nenhum trecho de documento foi recuperado para esta pergunta. "
            'Responda exatamente: "Não tenho contexto suficiente nos '
            "documentos fornecidos para responder a essa pergunta com "
            'segurança."\n\nPergunta: ?'
        ),
    )

    assert "Não tenho contexto suficiente" in completion.text


@pytest.mark.unit
def test_mock_metrics_are_deterministic_and_zero_cost() -> None:
    client = MockLlmClient()

    completion = client.complete(
        system_prompt="",
        user_prompt="Trechos de documentos disponíveis para consulta:\n[1]",
    )

    assert completion.tokens_used == 0
    assert completion.cost_usd == 0.0
    assert completion.latency_ms == 1
    assert completion.model == "mock"


@pytest.mark.unit
def test_mock_is_deterministic_across_calls() -> None:
    """Mesma entrada → mesma saída, sempre."""
    client = MockLlmClient()
    user_prompt = "Trechos de documentos disponíveis para consulta:\n[1] foo"

    first = client.complete("sys", user_prompt)
    second = client.complete("sys", user_prompt)

    assert first.text == second.text
    assert first.tokens_used == second.tokens_used
    assert first.model == second.model
