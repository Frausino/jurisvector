"""Testes unitários da entidade User.

Foco em provar que a regra de autorização do multi-tenant
(núcleo do controle contra BOLA / OWASP API1) está correta
e isolada na camada de domínio, sem depender de banco, HTTP
ou framework algum.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole


@pytest.fixture
def common_user() -> User:
    """Usuário comum (role=user) fixo para testes de autorização."""
    return User(
        email="user1@docuvector.local",
        password_hash="$2b$12$fake_bcrypt_hash_for_unit_test_only",
        role=UserRole.USER,
    )


@pytest.fixture
def admin_user() -> User:
    """Administrador (role=admin) fixo para testes de autorização."""
    return User(
        email="admin@docuvector.local",
        password_hash="$2b$12$fake_bcrypt_hash_for_unit_test_only",
        role=UserRole.ADMIN,
    )


@pytest.mark.unit
def test_user_can_access_own_document(common_user: User) -> None:
    """Usuário comum deve enxergar documentos cujo owner_id seja o seu próprio id."""
    own_document_owner_id = common_user.id

    assert common_user.can_access_document_owned_by(own_document_owner_id) is True


@pytest.mark.unit
def test_user_cannot_access_other_users_document(common_user: User) -> None:
    """Usuário comum NÃO deve enxergar documentos de outros usuários.

    Este é o núcleo do controle contra BOLA (OWASP API1:2023). Se este
    teste falhar, a regra de autorização do sistema está quebrada e
    documentos privados podem vazar entre tenants.
    """
    another_users_owner_id = uuid4()

    assert another_users_owner_id != common_user.id
    assert common_user.can_access_document_owned_by(another_users_owner_id) is False


@pytest.mark.unit
def test_admin_can_access_any_document(admin_user: User) -> None:
    """Administrador deve enxergar documento de qualquer usuário do sistema."""
    arbitrary_owner_id = uuid4()

    assert admin_user.is_admin() is True
    assert admin_user.can_access_document_owned_by(arbitrary_owner_id) is True


@pytest.mark.unit
def test_user_entity_is_immutable_after_creation(common_user: User) -> None:
    """Entidade User é frozen: tentativa de mutação deve falhar.

    Imutabilidade evita que código em camadas externas (router, middleware)
    altere acidentalmente atributos sensíveis como `role` ou `is_active`,
    o que poderia constituir escalonamento de privilégio silencioso.
    """
    with pytest.raises(AttributeError):
        common_user.role = UserRole.ADMIN  # type: ignore[misc]

    with pytest.raises(AttributeError):
        common_user.is_active = False  # type: ignore[misc]
