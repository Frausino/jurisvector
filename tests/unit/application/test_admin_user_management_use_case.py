"""Testes unit do AdminUserManagementUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from docuvector.application.admin_user_management_use_case import (
    AdminUserManagementUseCase,
)
from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, UserRole
from docuvector.domain.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
)


# =============================================================
# Fakes (reaproveitam padrão dos outros testes)
# =============================================================
class _InMemoryUserRepository:
    def __init__(self) -> None:
        self._users_by_id: dict[UUID, User] = {}

    def add(self, user: User) -> None:
        self._users_by_id[user.id] = user

    def find_by_email(self, email: str) -> User | None:
        for user in self._users_by_id.values():
            if user.email == email.lower():
                return user
        return None

    def find_by_id(self, user_id: UUID) -> User | None:
        return self._users_by_id.get(user_id)

    def save(self, user: User) -> User:
        self._users_by_id[user.id] = user
        return user

    def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[User]:
        return list(self._users_by_id.values())[offset : offset + limit]

    def count_all(self) -> int:
        return len(self._users_by_id)

    def delete_by_id(self, user_id: UUID) -> bool:
        return self._users_by_id.pop(user_id, None) is not None


class _FakeHasher:
    def hash(self, plain_password: str) -> str:
        return f"hash::{plain_password}"

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return password_hash == f"hash::{plain_password}"


class _AcceptAllPolicy:
    def validate(self, plain_password: str, owner_identifier: str | None = None) -> None:
        return None


class _InMemoryAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        return self.events[offset : offset + limit]


AdminSetup = tuple[
    AdminUserManagementUseCase,
    _InMemoryUserRepository,
    _InMemoryAuditRepository,
    User,
]


# =============================================================
# Helpers
# =============================================================
def _build_user(role: UserRole = UserRole.USER, email: str = "test@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        password_hash="hash::dummy",
        role=role,
        is_active=True,
    )


@pytest.fixture
def admin_setup() -> AdminSetup:
    users = _InMemoryUserRepository()
    audit = _InMemoryAuditRepository()
    use_case = AdminUserManagementUseCase(
        user_repository=users,
        password_hasher=_FakeHasher(),
        password_policy=_AcceptAllPolicy(),
        audit_repository=audit,
    )
    acting_admin = _build_user(role=UserRole.ADMIN, email="admin@example.com")
    users.add(acting_admin)
    return use_case, users, audit, acting_admin


# =============================================================
# list_users
# =============================================================
@pytest.mark.unit
def test_list_users_returns_page(admin_setup: AdminSetup) -> None:
    use_case, users, _audit, _admin = admin_setup
    for index in range(3):
        users.add(_build_user(email=f"user{index}@example.com"))

    page = use_case.list_users(limit=10, offset=0)

    # admin (já no setup) + 3 novos = 4
    assert page.total == 4
    assert len(page.items) == 4


@pytest.mark.unit
def test_list_users_clamps_excessive_limit(admin_setup: AdminSetup) -> None:
    use_case, _users, _audit, _admin = admin_setup
    page = use_case.list_users(limit=1000, offset=0)
    assert page.limit == 200  # MAX_PAGE_SIZE


# =============================================================
# create_user
# =============================================================
@pytest.mark.unit
def test_admin_creates_user_with_assigned_role(admin_setup: AdminSetup) -> None:
    use_case, users, audit, admin = admin_setup

    created = use_case.create_user(
        acting_admin_id=admin.id,
        email="new@example.com",
        plain_password="senhamuitolonga",
        role=UserRole.USER,
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert created.role is UserRole.USER
    assert users.find_by_email("new@example.com") is not None
    assert any(event.action is AuditAction.USER_CREATED_BY_ADMIN for event in audit.events)


@pytest.mark.unit
def test_admin_can_create_another_admin(admin_setup: AdminSetup) -> None:
    use_case, _users, _audit, admin = admin_setup

    created = use_case.create_user(
        acting_admin_id=admin.id,
        email="newadmin@example.com",
        plain_password="senhamuitolonga",
        role=UserRole.ADMIN,
        client_ip=None,
        user_agent=None,
    )

    assert created.role is UserRole.ADMIN


@pytest.mark.unit
def test_admin_cannot_create_duplicate_email(admin_setup: AdminSetup) -> None:
    use_case, _users, _audit, admin = admin_setup
    use_case.create_user(
        acting_admin_id=admin.id,
        email="x@example.com",
        plain_password="senhamuitolonga",
        role=UserRole.USER,
        client_ip=None,
        user_agent=None,
    )

    with pytest.raises(DuplicateResourceError):
        use_case.create_user(
            acting_admin_id=admin.id,
            email="x@example.com",
            plain_password="outrasenhalonga",
            role=UserRole.USER,
            client_ip=None,
            user_agent=None,
        )


# =============================================================
# delete_user
# =============================================================
@pytest.mark.unit
def test_admin_deletes_target_user(admin_setup: AdminSetup) -> None:
    use_case, users, audit, admin = admin_setup
    target_user = _build_user(email="victim@example.com")
    users.add(target_user)

    use_case.delete_user(
        acting_admin_id=admin.id,
        target_user_id=target_user.id,
        client_ip=None,
        user_agent=None,
    )

    assert users.find_by_id(target_user.id) is None
    assert any(event.action is AuditAction.USER_DELETED for event in audit.events)


@pytest.mark.unit
def test_admin_cannot_delete_self(admin_setup: AdminSetup) -> None:
    use_case, users, _audit, admin = admin_setup

    with pytest.raises(AuthorizationError, match="excluir a própria"):
        use_case.delete_user(
            acting_admin_id=admin.id,
            target_user_id=admin.id,
            client_ip=None,
            user_agent=None,
        )

    # Admin continua no banco.
    assert users.find_by_id(admin.id) is not None


@pytest.mark.unit
def test_delete_unknown_user_raises_not_found(admin_setup: AdminSetup) -> None:
    use_case, _users, _audit, admin = admin_setup

    with pytest.raises(ResourceNotFoundError):
        use_case.delete_user(
            acting_admin_id=admin.id,
            target_user_id=uuid4(),
            client_ip=None,
            user_agent=None,
        )


# =============================================================
# change_role
# =============================================================
@pytest.mark.unit
def test_admin_promotes_user_to_admin(admin_setup: AdminSetup) -> None:
    use_case, users, audit, admin = admin_setup
    target_user = _build_user(role=UserRole.USER, email="future_admin@example.com")
    users.add(target_user)

    updated = use_case.change_role(
        acting_admin_id=admin.id,
        target_user_id=target_user.id,
        new_role=UserRole.ADMIN,
        client_ip=None,
        user_agent=None,
    )

    assert updated.role is UserRole.ADMIN
    assert any(event.action is AuditAction.USER_ROLE_CHANGED for event in audit.events)


@pytest.mark.unit
def test_admin_cannot_demote_self(admin_setup: AdminSetup) -> None:
    use_case, _users, _audit, admin = admin_setup

    with pytest.raises(AuthorizationError, match="rebaixar"):
        use_case.change_role(
            acting_admin_id=admin.id,
            target_user_id=admin.id,
            new_role=UserRole.USER,
            client_ip=None,
            user_agent=None,
        )


@pytest.mark.unit
def test_change_role_to_same_role_is_noop(admin_setup: AdminSetup) -> None:
    """Mudar para o mesmo papel é idempotente: não falha, não audita."""
    use_case, users, audit, admin = admin_setup
    target_user = _build_user(role=UserRole.USER)
    users.add(target_user)

    audit_count_before = len(audit.events)
    result = use_case.change_role(
        acting_admin_id=admin.id,
        target_user_id=target_user.id,
        new_role=UserRole.USER,
        client_ip=None,
        user_agent=None,
    )

    assert result.role is UserRole.USER
    assert len(audit.events) == audit_count_before  # nada novo no audit
