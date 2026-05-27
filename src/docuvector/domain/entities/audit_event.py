"""Entidade de evento de auditoria."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from docuvector.domain.enums import AuditAction, AuditStatus


def _utc_now() -> datetime:
    """Timestamp timezone-aware em UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Registro de uma ação sensível para rastreabilidade.

    Campos opcionais (user_id, resource_id, ip_address) cobrem cenários
    onde a ação ocorre fora de uma sessão autenticada, como tentativa
    de login com email inexistente.
    """

    action: AuditAction
    status: AuditStatus
    resource_type: str
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    resource_id: UUID | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
