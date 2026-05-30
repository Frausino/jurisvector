"""Implementações concretas de `EmbeddingProvider`."""

from docuvector.infrastructure.embeddings.factory import (
    list_available_providers,
    resolve_embedder,
)
from docuvector.infrastructure.embeddings.openai_embedder import OpenAiEmbedder
from docuvector.infrastructure.embeddings.sentence_transformers_embedder import (
    SentenceTransformersEmbedder,
)

__all__ = [
    "OpenAiEmbedder",
    "SentenceTransformersEmbedder",
    "list_available_providers",
    "resolve_embedder",
]
