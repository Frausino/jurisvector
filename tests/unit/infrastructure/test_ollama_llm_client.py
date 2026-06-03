"""Testes unit do OllamaLlmClient (httpx mockado)."""

from __future__ import annotations

import httpx
import pytest

from docuvector.domain.exceptions import LlmGenerationError
from docuvector.infrastructure.llm.ollama_llm_client import OllamaLlmClient


def _make_client_with_mock_transport(
    mock_response_payload: dict[str, object] | None = None,
    raise_http_error: bool = False,
) -> OllamaLlmClient:
    """Constrói um OllamaLlmClient cujo httpx é roteado para um MockTransport.

    Truque: monkeypatch o `httpx.post` global temporariamente não é
    necessário porque o cliente usa `httpx.post` direto. Usamos
    `pytest.MonkeyPatch` no teste para substituir essa chamada.
    """
    return OllamaLlmClient(
        base_url="http://localhost:11434",
        model="qwen2.5:7b",
        timeout_seconds=5.0,
    )


@pytest.mark.unit
def test_complete_parses_message_content_and_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resposta válida do Ollama → LlmCompletion com texto e tokens."""
    fake_payload = {
        "model": "qwen2.5:7b",
        "message": {"role": "assistant", "content": "Resposta gerada [1]."},
        "prompt_eval_count": 120,
        "eval_count": 35,
        "total_duration": 1_500_000_000,
    }

    def fake_post(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json=fake_payload,
            request=httpx.Request(
                "POST",
                "http://localhost:11434/api/chat",
            ),
        )

    monkeypatch.setattr(
        "docuvector.infrastructure.llm.ollama_llm_client.httpx.post",
        fake_post,
    )
    client = _make_client_with_mock_transport()
    completion = client.complete(system_prompt="sys", user_prompt="user pergunta")

    assert completion.text == "Resposta gerada [1]."
    assert completion.tokens_used == 155
    assert completion.cost_usd == 0.0
    assert completion.model == "qwen2.5:7b"
    assert completion.latency_ms >= 0


@pytest.mark.unit
def test_complete_raises_llm_error_when_http_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falha HTTP (404, 500, timeout) → LlmGenerationError preservando causa."""

    def failing_post(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("conexão recusada")

    monkeypatch.setattr(
        "docuvector.infrastructure.llm.ollama_llm_client.httpx.post",
        failing_post,
    )

    client = _make_client_with_mock_transport()

    with pytest.raises(LlmGenerationError) as exception_info:
        client.complete(system_prompt="sys", user_prompt="user")

    assert "Ollama" in str(exception_info.value)
    assert "localhost:11434" in str(exception_info.value)


@pytest.mark.unit
def test_base_url_trailing_slash_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`base_url` com barra final NÃO deve gerar `//api/chat`."""
    captured_urls: list[str] = []

    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        captured_urls.append(url)

        return httpx.Response(
            status_code=200,
            json={
                "model": "qwen2.5:7b",
                "message": {
                    "role": "assistant",
                    "content": "ok",
                },
                "prompt_eval_count": 1,
                "eval_count": 1,
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "docuvector.infrastructure.llm.ollama_llm_client.httpx.post",
        fake_post,
    )

    client = OllamaLlmClient(
        base_url="http://localhost:11434/",
        model="qwen2.5:7b",
    )

    client.complete(
        system_prompt="sys",
        user_prompt="user",
    )

    assert captured_urls == [
        "http://localhost:11434/api/chat",
    ]


@pytest.mark.unit
def test_complete_rejects_empty_user_prompt() -> None:
    """Sem chamar HTTP: validação acontece antes."""
    client = _make_client_with_mock_transport()

    with pytest.raises(LlmGenerationError, match="vazio"):
        client.complete(system_prompt="sys", user_prompt="   ")
