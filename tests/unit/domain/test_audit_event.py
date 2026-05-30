"""Testes unit da entidade AuditEvent após desacoplamento."""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest

from docuvector.domain.entities import AuditEvent
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole


@pytest.mark.unit
def test_audit_event_has_optional_actor_snapshot_defaulting_to_none() -> None:
    """Sem actor (ex.: login falho com email inexistente), snapshots ficam None."""
    event = AuditEvent(
        action=AuditAction.LOGIN_FAILED,
        status=AuditStatus.FAILURE,
        resource_type="user",
    )

    assert event.actor_user_id is None
    assert event.actor_email is None
    assert event.actor_role is None
    assert event.correlation_id is None
    assert event.metadata == {}


@pytest.mark.unit
def test_audit_event_carries_full_actor_snapshot_when_provided() -> None:
    """Snapshots viajam com o evento, independem de JOIN com `users`."""
    actor_id = uuid4()
    correlation_id = uuid4()
    event = AuditEvent(
        action=AuditAction.LOGIN_SUCCESS,
        status=AuditStatus.SUCCESS,
        resource_type="user",
        actor_user_id=actor_id,
        actor_email="alice@example.com",
        actor_role=UserRole.USER,
        correlation_id=correlation_id,
        metadata={"key": "value"},
    )

    assert event.actor_user_id == actor_id
    assert event.actor_email == "alice@example.com"
    assert event.actor_role is UserRole.USER
    assert event.correlation_id == correlation_id


@pytest.mark.unit
def test_audit_event_is_immutable() -> None:
    """Eventos NÃO podem ser modificados após criação (ledger append-only)."""
    event = AuditEvent(
        action=AuditAction.LOGIN_SUCCESS,
        status=AuditStatus.SUCCESS,
        resource_type="user",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.resource_type = "outro"  # type: ignore[misc]


@pytest.mark.unit
def test_audit_event_preserves_actor_id_even_if_user_deleted() -> None:
    """`actor_user_id` NÃO tem FK; valor persiste mesmo após o usuário ser deletado.

    A entidade aceita qualquer UUID, refletindo essa semântica. A
    migration 0004 garante a mesma propriedade no schema.
    """
    historical_actor = uuid4()
    event = AuditEvent(
        action=AuditAction.USER_DELETED,
        status=AuditStatus.SUCCESS,
        resource_type="user",
        actor_user_id=historical_actor,
        actor_email="deletado@example.com",
        actor_role=UserRole.ADMIN,
    )

    assert event.actor_user_id == historical_actor
