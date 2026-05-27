"""Implementação SQLAlchemy do `AuditRepository`.

Decisão arquitetural: cada `append` abre uma sessão própria, commita e
fecha, **independente** da transação do request HTTP.

Motivo: audit log precisa persistir mesmo quando a transação principal
sofre rollback (ex.: login falho levantando `AuthenticationError`).
Padrão recomendado por NIST SP 800-53 AU-2 (Audit Events): registros
de auditoria são autônomos e não devem ser desfeitos junto com o
fluxo de negócio que os originou.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from docuvector.domain.entities import AuditEvent
from docuvector.domain.enums import AuditAction, AuditStatus
from docuvector.infrastructure.persistence.models import AuditLogModel


class SqlAlchemyAuditRepository:
    """Persistência append-only de eventos de auditoria.

    Aceita um `sessionmaker` em vez de uma `Session` para poder abrir
    transações independentes do fluxo principal.
    Satisfaz estruturalmente `domain.interfaces.AuditRepository`.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(self, event: AuditEvent) -> None:
        record = AuditLogModel(
            id=event.id,
            user_id=event.user_id,
            action=event.action,
            status=event.status,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            event_metadata=event.metadata or None,
            created_at=event.created_at,
        )
        # Sessão autônoma: append + commit imediato, independente da
        # transação principal. Erros aqui são logados via structlog
        # mas NÃO devem interromper o fluxo de negócio.
        with self._session_factory() as audit_session:
            audit_session.add(record)
            audit_session.commit()

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        with self._session_factory() as read_session:
            statement = (
                select(AuditLogModel)
                .order_by(AuditLogModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            records = read_session.scalars(statement).all()
            return [_to_entity(record) for record in records]


def _to_entity(record: AuditLogModel) -> AuditEvent:
    """Converte modelo ORM para entidade pura de domínio."""
    return AuditEvent(
        id=record.id,
        user_id=record.user_id,
        action=AuditAction(record.action),
        status=AuditStatus(record.status),
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        ip_address=record.ip_address,
        user_agent=record.user_agent,
        metadata=record.event_metadata or {},
        created_at=record.created_at,
    )
