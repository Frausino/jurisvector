"""Entidade DocumentChunk da camada de domínio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from docuvector.domain.enums import EmbeddingProviderName


def _utc_now() -> datetime:
    """Timestamp timezone-aware em UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """Fragmento de texto de um documento, pronto para vetorização.

    `owner_id` é denormalizado a partir do Document para permitir filtros
    multi-tenant em queries de retrieval sem JOIN. Custo de espaço é
    desprezível diante do benefício de simplicidade e performance.

    `embedding_provider`, `embedding_model` e `embedding_dimensions` são
    persistidos para a Sprint 4 (benchmark entre provedores e métricas
    de compressão exigem rastrear de onde cada vetor veio).
    """

    document_id: UUID
    owner_id: UUID
    chunk_index: int
    text: str
    token_count: int
    embedding_provider: EmbeddingProviderName
    embedding_model: str
    embedding_dimensions: int
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utc_now)

    def is_first_chunk(self) -> bool:
        """Conveniência semântica para citações e snippets."""
        return self.chunk_index == 0
