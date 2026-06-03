"""Resolução do `LlmClient` a partir do nome do provider.

Espelha o padrão de `infrastructure/embeddings/factory.py`:
cada provider concreto é construído UMA vez por processo (`@lru_cache`)
e a factory devolve a instância existente.

A escolha do provider vem da request HTTP (campo `llm_provider` em
`AskRequest`), nunca de um singleton fixo no `deps.py`. Isso permite
ao usuário alternar entre modos no front (local/cloud/mock) sem
reiniciar o processo.

Testes que mutam Settings (`monkeypatch.setenv`) chamam
`reset_factory_caches()` para invalidar instâncias em cache. A função
é pública por design: a alternativa (testes importando `_build_*`
private) gerava acoplamento entre teste e internals da factory.
"""

from __future__ import annotations

from functools import lru_cache

from docuvector.config.settings import Settings, get_settings
from docuvector.domain.enums import LlmProviderName
from docuvector.domain.exceptions import LlmGenerationError
from docuvector.domain.interfaces.llm_client import LlmClient
from docuvector.infrastructure.llm.mock_llm_client import MockLlmClient
from docuvector.infrastructure.llm.ollama_llm_client import OllamaLlmClient
from docuvector.infrastructure.llm.openai_llm_client import OpenAiLlmClient


@lru_cache(maxsize=1)
def _build_openai_client() -> OpenAiLlmClient:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    return OpenAiLlmClient(
        api_key=api_key,
        model=settings.openai_llm_model,
        temperature=settings.openai_llm_temperature,
        max_tokens=settings.openai_llm_max_tokens,
    )


@lru_cache(maxsize=1)
def _build_ollama_client() -> OllamaLlmClient:
    settings = get_settings()
    return OllamaLlmClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        temperature=settings.openai_llm_temperature,
        max_tokens=settings.openai_llm_max_tokens,
    )


@lru_cache(maxsize=1)
def _build_mock_client() -> MockLlmClient:
    return MockLlmClient()


def resolve_llm_client(provider_name: LlmProviderName) -> LlmClient:
    """Devolve o `LlmClient` correspondente ao provider solicitado.

    Levanta `LlmGenerationError` se o provider exigir credenciais
    ausentes (caso típico: usuário escolheu OPENAI sem chave). A
    falha vem cedo aqui, antes do `complete()`, para devolver 502
    com diagnóstico claro no router.
    """
    if provider_name is LlmProviderName.OPENAI:
        settings = get_settings()
        if not settings.openai_api_key or not settings.openai_api_key.get_secret_value():
            raise LlmGenerationError(
                "Provedor OpenAI selecionado, mas OPENAI_API_KEY não está configurada."
            )
        return _build_openai_client()

    if provider_name is LlmProviderName.OLLAMA:
        return _build_ollama_client()

    if provider_name is LlmProviderName.MOCK:
        return _build_mock_client()

    raise LlmGenerationError(f"Provedor de LLM não suportado: {provider_name.value}.")


def list_available_providers(
    settings: Settings | None = None,
) -> list[LlmProviderName]:
    """Lista provedores viáveis no ambiente atual.

    Política:
    - `MOCK` sempre disponível (não tem dependência externa).
    - `OLLAMA` sempre listado: a UX deve permitir tentar, e a
      indisponibilidade do servidor vira `LlmGenerationError` na chamada
      (502), com mensagem clara. Ocultar aqui exigiria um health-check
      síncrono que atrasaria toda página de configuração.
    - `OPENAI` listado apenas se `OPENAI_API_KEY` está presente.
    """
    current_settings = settings or get_settings()
    available: list[LlmProviderName] = [LlmProviderName.MOCK, LlmProviderName.OLLAMA]
    if current_settings.openai_api_key and current_settings.openai_api_key.get_secret_value():
        available.append(LlmProviderName.OPENAI)
    return available


def reset_factory_caches() -> None:
    """Invalida todos os caches @lru_cache da factory.

    Uso típico: fixtures de teste que mutam variáveis de ambiente
    (ex.: `monkeypatch.setenv("OPENAI_API_KEY", ...)`) precisam que a
    próxima chamada a `resolve_llm_client` reflita o novo estado dos
    Settings, não a instância construída antes da mutação.

    Função pública por design, em vez de testes importarem
    `_build_*_client` private.
    """
    _build_openai_client.cache_clear()
    _build_ollama_client.cache_clear()
    _build_mock_client.cache_clear()
