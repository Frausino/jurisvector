"""Resolução de qual `EmbeddingProvider` usar a partir do nome.

A escolha do provider chega via UX (usuário decide ao subir documento)
ou via API (campo `embedding_provider` no upload). Esta factory traduz
o nome enum para a instância concreta apropriada, garantindo singleton
por provider (carregar o E5 a cada request seria proibitivo).
"""

from __future__ import annotations

from functools import lru_cache

from docuvector.config.settings import Settings, get_settings
from docuvector.domain.enums import EmbeddingProviderName
from docuvector.domain.exceptions import EmbeddingGenerationError
from docuvector.domain.interfaces import EmbeddingProvider
from docuvector.infrastructure.embeddings.openai_embedder import OpenAiEmbedder
from docuvector.infrastructure.embeddings.sentence_transformers_embedder import (
    SentenceTransformersEmbedder,
)


@lru_cache(maxsize=1)
def _build_openai_embedder() -> OpenAiEmbedder:
    """Constrói o embedder OpenAI uma única vez por processo."""
    settings = get_settings()
    return OpenAiEmbedder(
        api_key=settings.openai_api_key.get_secret_value() if settings.openai_api_key else "",
        model_name=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
    )


@lru_cache(maxsize=1)
def _build_sentence_transformers_embedder() -> SentenceTransformersEmbedder:
    """Constrói o embedder local uma única vez (carrega modelo em RAM)."""
    settings = get_settings()
    return SentenceTransformersEmbedder(
        model_name=settings.sentence_transformers_model,
        dimensions=settings.sentence_transformers_dimensions,
        cache_folder=str(settings.hf_home),
    )


def resolve_embedder(provider_name: EmbeddingProviderName) -> EmbeddingProvider:
    """Devolve o embedder correspondente ao nome solicitado.

    Levanta `EmbeddingGenerationError` se o provider exigir credenciais
    ausentes (caso típico do usuário escolher OpenAI sem ter chave).
    """
    if provider_name is EmbeddingProviderName.OPENAI:
        embedder = _build_openai_embedder()
        if not embedder.dimensions:
            raise EmbeddingGenerationError(
                "OpenAI selecionado mas as configurações estão incompletas."
            )
        return embedder

    if provider_name is EmbeddingProviderName.SENTENCE_TRANSFORMERS:
        return _build_sentence_transformers_embedder()

    raise EmbeddingGenerationError(f"Provedor de embeddings não suportado: {provider_name.value}.")


def list_available_providers(settings: Settings | None = None) -> list[EmbeddingProviderName]:
    """Lista provedores disponíveis no ambiente atual.

    Útil para a UX exibir apenas opções viáveis: se a `OPENAI_API_KEY`
    não está configurada, não faz sentido oferecer OpenAI no select.
    """
    current_settings = settings or get_settings()
    available: list[EmbeddingProviderName] = [EmbeddingProviderName.SENTENCE_TRANSFORMERS]
    if current_settings.openai_api_key and current_settings.openai_api_key.get_secret_value():
        available.append(EmbeddingProviderName.OPENAI)
    return available
