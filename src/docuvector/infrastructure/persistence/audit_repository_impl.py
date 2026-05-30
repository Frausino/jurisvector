"""Implementação SQLAlchemy do `AuditRepository`.

Decisão arquitetural: cada `append` abre uma sessão própria, commita e
fecha, **independente** da transação do request HTTP.

Motivo: audit log é ledger forense autônomo (NIST SP 800-53 AU-2).
Registros sobrevivem a rollback da transação principal. A ausência de
foreign key contra `users` (após migration 0004) elimina dependência
de ordem de commit: o evento de auditoria pode ser inserido em
qualquer momento, sem se importar com o estado da sessão do usuário.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from docuvector.domain.entities import AuditEvent
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole
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
            actor_user_id=event.actor_user_id,
            actor_email=event.actor_email,
            actor_role=event.actor_role,
            action=event.action,
            status=event.status,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            correlation_id=event.correlation_id,
            event_metadata=event.metadata or None,
            created_at=event.created_at,
        )
        # Sessão autônoma: append + commit imediato, independente da
        # transação principal.
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
        actor_user_id=record.actor_user_id,
        actor_email=record.actor_email,
        actor_role=UserRole(record.actor_role) if record.actor_role is not None else None,
        action=AuditAction(record.action),
        status=AuditStatus(record.status),
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        ip_address=record.ip_address,
        user_agent=record.user_agent,
        correlation_id=record.correlation_id,
        metadata=record.event_metadata or {},
        created_at=record.created_at,
    )
