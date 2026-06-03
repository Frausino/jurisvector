"""Testes unit da factory `resolve_llm_client` e `list_available_providers`."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from docuvector.config.settings import get_settings
from docuvector.domain.enums import LlmProviderName
from docuvector.domain.exceptions import LlmGenerationError
from docuvector.infrastructure.llm.factory import (
    list_available_providers,
    reset_factory_caches,
    resolve_llm_client,
)
from docuvector.infrastructure.llm.mock_llm_client import MockLlmClient
from docuvector.infrastructure.llm.ollama_llm_client import OllamaLlmClient
from docuvector.infrastructure.llm.openai_llm_client import OpenAiLlmClient


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Garante isolamento de estado entre testes que mutam env vars."""
    reset_factory_caches()
    get_settings.cache_clear()
    yield
    reset_factory_caches()
    get_settings.cache_clear()


@pytest.mark.unit
def test_resolve_mock_provider_returns_mock_client() -> None:
    client = resolve_llm_client(LlmProviderName.MOCK)
    assert isinstance(client, MockLlmClient)


@pytest.mark.unit
def test_resolve_ollama_provider_returns_ollama_client() -> None:
    client = resolve_llm_client(LlmProviderName.OLLAMA)
    assert isinstance(client, OllamaLlmClient)


@pytest.mark.unit
def test_resolve_returns_same_instance_across_calls() -> None:
    """`@lru_cache` garante singleton por provider no processo."""
    first = resolve_llm_client(LlmProviderName.MOCK)
    second = resolve_llm_client(LlmProviderName.MOCK)
    assert first is second


@pytest.mark.unit
def test_resolve_openai_without_api_key_raises_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI sem chave deve falhar cedo na factory, não na chamada."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(LlmGenerationError, match="OPENAI_API_KEY"):
        resolve_llm_client(LlmProviderName.OPENAI)


@pytest.mark.unit
def test_resolve_openai_with_api_key_returns_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-stub")
    get_settings.cache_clear()

    client = resolve_llm_client(LlmProviderName.OPENAI)
    assert isinstance(client, OpenAiLlmClient)


@pytest.mark.unit
def test_list_available_always_includes_mock_and_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    available = list_available_providers()
    assert LlmProviderName.MOCK in available
    assert LlmProviderName.OLLAMA in available
    assert LlmProviderName.OPENAI not in available


@pytest.mark.unit
def test_list_available_includes_openai_when_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-anything")
    get_settings.cache_clear()

    available = list_available_providers()
    assert LlmProviderName.OPENAI in available


@pytest.mark.unit
def test_reset_factory_caches_invalidates_existing_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Após reset, próximas chamadas constroem instância NOVA."""
    first_mock = resolve_llm_client(LlmProviderName.MOCK)
    reset_factory_caches()
    second_mock = resolve_llm_client(LlmProviderName.MOCK)
    # mesmas instâncias compartilhadas dentro do lru_cache; reset
    # quebra o cache, então estas DEVEM ser objetos diferentes.
    assert first_mock is not second_mock
