"""Entidade Document da camada de domínio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from docuvector.domain.enums import DocumentStatus, FileFormat


def _utc_now() -> datetime:
    """Timestamp timezone-aware em UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Document:
    """Documento ingerido por um usuário no pipeline RAG.

    `owner_id` é obrigatório porque toda lógica de retrieval filtra por
    dono (defesa contra BOLA). `checksum_sha256` permite detectar uploads
    duplicados antes mesmo de iniciar a extração; ver constraint UNIQUE
    (owner_id, checksum_sha256) na migration 0003.

    Frozen + slots para evitar mutação acidental e reduzir footprint.
    """

    owner_id: UUID
    filename: str
    file_format: FileFormat
    size_bytes: int
    checksum_sha256: str
    id: UUID = field(default_factory=uuid4)
    status: DocumentStatus = DocumentStatus.UPLOADED
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def is_ready_for_retrieval(self) -> bool:
        """Apenas documentos com embeddings completos participam de queries."""
        return self.status is DocumentStatus.EMBEDDED

    def is_terminally_failed(self) -> bool:
        """Documento que não pode mais progredir no pipeline."""
        return self.status is DocumentStatus.FAILED
