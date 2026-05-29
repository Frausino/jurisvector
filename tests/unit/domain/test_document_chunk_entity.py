"""Testes unitários da entidade DocumentChunk."""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest

from docuvector.domain.entities import DocumentChunk
from docuvector.domain.enums import EmbeddingProviderName


def _build_chunk(chunk_index: int = 0) -> DocumentChunk:
    return DocumentChunk(
        document_id=uuid4(),
        owner_id=uuid4(),
        chunk_index=chunk_index,
        text="texto",
        token_count=10,
        embedding_provider=EmbeddingProviderName.OPENAI,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )


@pytest.mark.unit
def test_chunk_is_frozen_and_uses_slots() -> None:
    """DocumentChunk é imutável e não aceita atributos extras."""
    chunk = _build_chunk()

    with pytest.raises(dataclasses.FrozenInstanceError):
        chunk.text = "outro"  # type: ignore[misc]

    # Em Python 3.12, dataclass(frozen=True, slots=True) pode lançar TypeError
    # ao tentar adicionar atributos inexistentes. O requisito é impedir a mutação.
    with pytest.raises((AttributeError, TypeError)):
        chunk.extra = 1  # type: ignore[attr-defined]


@pytest.mark.unit
def test_is_first_chunk_detects_index_zero() -> None:
    """Conveniência semântica usada em citações e snippets."""
    assert _build_chunk(chunk_index=0).is_first_chunk() is True
    assert _build_chunk(chunk_index=1).is_first_chunk() is False


@pytest.mark.unit
def test_chunk_carries_embedding_metadata() -> None:
    """Metadados de embedding persistem para benchmark da Sprint 4."""
    chunk = DocumentChunk(
        document_id=uuid4(),
        owner_id=uuid4(),
        chunk_index=3,
        text="parágrafo",
        token_count=42,
        embedding_provider=EmbeddingProviderName.SENTENCE_TRANSFORMERS,
        embedding_model="intfloat/multilingual-e5-small",
        embedding_dimensions=384,
    )

    assert chunk.embedding_provider is EmbeddingProviderName.SENTENCE_TRANSFORMERS
    assert chunk.embedding_model == "intfloat/multilingual-e5-small"
    assert chunk.embedding_dimensions == 384
