"""Testes unit do RegisterUserUseCase com defesa anti-enumeração."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import pytest

from docuvector.application.register_user_use_case import RegisterUserUseCase
from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole
from docuvector.domain.exceptions import ValidationError


# =============================================================
# Fakes
# =============================================================
class _InMemoryUserRepository:
    def __init__(self) -> None:
        self._users_by_email: dict[str, User] = {}

    def find_by_email(self, email: str) -> User | None:
        return self._users_by_email.get(email.lower())

    def find_by_id(self, user_id: UUID) -> User | None:
        for user in self._users_by_email.values():
            if user.id == user_id:
                return user
        return None

    def save(self, user: User) -> User:
        self._users_by_email[user.email.lower()] = user
        return user

    def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[User]:
        return list(self._users_by_email.values())[offset : offset + limit]

    def count_all(self) -> int:
        return len(self._users_by_email)

    def delete_by_id(self, user_id: UUID) -> bool:
        for email, user in list(self._users_by_email.items()):
            if user.id == user_id:
                del self._users_by_email[email]
                return True
        return False


class _CountingHasher:
    """Hasher fake que conta quantas vezes hash() foi chamado.

    Usado para confirmar que o caminho "duplicado" também chama o hash
    (defesa contra timing).
    """

    def __init__(self) -> None:
        self.hash_call_count = 0

    def hash(self, plain_password: str) -> str:
        self.hash_call_count += 1
        return f"hash::{plain_password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return hashed_password == f"hash::{plain_password}"


class _AcceptAllPolicy:
    def validate(self, plain_password: str, owner_identifier: str | None = None) -> None:
        if not plain_password:
            raise ValidationError("Senha vazia.")


class _RejectAllPolicy:
    def validate(self, plain_password: str, owner_identifier: str | None = None) -> None:
        raise ValidationError("Senha não atende à política.")


class _PolicyThatChecksIdentifier:
    """Policy que rejeita se identifier estiver vazio (prova que o
    use case passa o email para a política)."""

    def validate(self, plain_password: str, owner_identifier: str | None = None) -> None:
        if owner_identifier is None or not owner_identifier:
            raise ValidationError("Identifier era esperado mas veio None.")


class _InMemoryAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_paginated(
        self,
        offset: int,
        limit: int,
    ) -> list[AuditEvent]:
        return self.events[offset : offset + limit]


UseCaseWithFakes = tuple[
    RegisterUserUseCase,
    _InMemoryUserRepository,
    _InMemoryAuditRepository,
    _CountingHasher,
]


# =============================================================
# Fixtures
# =============================================================
@pytest.fixture
def use_case_with_fakes() -> tuple[
    RegisterUserUseCase,
    _InMemoryUserRepository,
    _InMemoryAuditRepository,
    _CountingHasher,
]:
    users = _InMemoryUserRepository()
    audit = _InMemoryAuditRepository()
    hasher = _CountingHasher()
    use_case = RegisterUserUseCase(
        user_repository=users,
        password_hasher=hasher,
        password_policy=_AcceptAllPolicy(),
        audit_repository=audit,
    )
    return use_case, users, audit, hasher


# =============================================================
# Happy path
# =============================================================
@pytest.mark.unit
def test_register_creates_user_with_role_user(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    use_case, users, _audit, _hasher = use_case_with_fakes

    result = use_case.register(
        email="alice@example.com",
        plain_password="senharobusta123",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert result.was_created is True
    assert result.user.role is UserRole.USER
    assert result.user.is_active is True
    assert result.user.email == "alice@example.com"
    assert users.find_by_email("alice@example.com") is not None


@pytest.mark.unit
def test_register_normalizes_email_to_lowercase(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    use_case, users, _audit, _hasher = use_case_with_fakes

    use_case.register(
        email="ALICE@Example.COM",
        plain_password="senhamuitorobusta",
        client_ip=None,
        user_agent=None,
    )

    assert users.find_by_email("alice@example.com") is not None


@pytest.mark.unit
def test_register_emits_success_audit(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    use_case, _users, audit, _hasher = use_case_with_fakes

    use_case.register(
        email="bob@example.com",
        plain_password="senhamuitorobusta",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    success_events = [
        e
        for e in audit.events
        if e.action is AuditAction.USER_REGISTERED and e.status is AuditStatus.SUCCESS
    ]
    assert len(success_events) == 1
    assert success_events[0].metadata is not None
    assert success_events[0].metadata["email"] == "bob@example.com"


# =============================================================
# Anti-enumeração (gap #3)
# =============================================================
@pytest.mark.unit
def test_register_duplicate_email_does_not_raise(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    """Email duplicado NÃO levanta exceção (defesa anti-enum)."""
    use_case, _users, _audit, _hasher = use_case_with_fakes
    use_case.register(
        email="alice@example.com",
        plain_password="senhamuitorobusta",
        client_ip=None,
        user_agent=None,
    )

    # Segunda tentativa NÃO deve levantar.
    result = use_case.register(
        email="alice@example.com",
        plain_password="outrasenhalonga",
        client_ip=None,
        user_agent=None,
    )

    assert result.was_created is False
    # O usuário retornado é o ORIGINAL.
    assert result.user.email == "alice@example.com"


@pytest.mark.unit
def test_duplicate_email_path_still_executes_hash_for_timing_parity(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    """Caminho de email duplicado executa hash dummy (custo igual ao real)."""
    use_case, _users, _audit, hasher = use_case_with_fakes
    use_case.register(
        email="alice@example.com",
        plain_password="senhamuitorobusta",
        client_ip=None,
        user_agent=None,
    )
    hash_count_after_first = hasher.hash_call_count

    use_case.register(
        email="alice@example.com",
        plain_password="outrasenhalonga",
        client_ip=None,
        user_agent=None,
    )

    # +1 hash call no caminho duplicado também.
    assert hasher.hash_call_count == hash_count_after_first + 1


@pytest.mark.unit
def test_duplicate_email_emits_failure_audit_for_forensics(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    """Audit registra a tentativa duplicada como FAILURE (visível só forense)."""
    use_case, _users, audit, _hasher = use_case_with_fakes
    use_case.register(
        email="alice@example.com",
        plain_password="senhamuitorobusta",
        client_ip="1.2.3.4",
        user_agent="probe",
    )

    use_case.register(
        email="alice@example.com",
        plain_password="outrasenhalonga",
        client_ip="1.2.3.4",
        user_agent="probe",
    )

    failure_events = [
        e
        for e in audit.events
        if e.action is AuditAction.USER_REGISTERED and e.status is AuditStatus.FAILURE
    ]
    assert len(failure_events) == 1
    assert failure_events[0].metadata is not None
    assert failure_events[0].metadata["reason"] == "email_already_registered"


@pytest.mark.unit
def test_dedup_is_case_insensitive(
    use_case_with_fakes: UseCaseWithFakes,
) -> None:
    use_case, _users, _audit, _hasher = use_case_with_fakes
    use_case.register(
        email="alice@example.com",
        plain_password="senhamuitorobusta",
        client_ip=None,
        user_agent=None,
    )

    result = use_case.register(
        email="ALICE@example.COM",
        plain_password="outrasenhalonga",
        client_ip=None,
        user_agent=None,
    )

    assert result.was_created is False


# =============================================================
# Validação de senha
# =============================================================
@pytest.mark.unit
def test_register_rejects_weak_password_via_policy() -> None:
    users = _InMemoryUserRepository()
    audit = _InMemoryAuditRepository()
    strict_use_case = RegisterUserUseCase(
        user_repository=users,
        password_hasher=_CountingHasher(),
        password_policy=_RejectAllPolicy(),
        audit_repository=audit,
    )

    with pytest.raises(ValidationError):
        strict_use_case.register(
            email="alice@example.com",
            plain_password="qualquer",
            client_ip=None,
            user_agent=None,
        )

    assert audit.events == []
    assert users.count_all() == 0


# =============================================================
# Gap #5: política RECEBE owner_identifier no fluxo real
# =============================================================
@pytest.mark.unit
def test_use_case_passes_owner_identifier_to_policy() -> None:
    """Garante que `validate(senha, owner_identifier=email)` é chamado."""
    users = _InMemoryUserRepository()
    audit = _InMemoryAuditRepository()
    use_case = RegisterUserUseCase(
        user_repository=users,
        password_hasher=_CountingHasher(),
        password_policy=_PolicyThatChecksIdentifier(),
        audit_repository=audit,
    )

    # Se o identifier NÃO chegasse, a policy levantaria ValidationError.
    use_case.register(
        email="alice@example.com",
        plain_password="senhamuitorobusta",
        client_ip=None,
        user_agent=None,
    )
