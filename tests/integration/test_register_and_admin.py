"""Testes de integração de registro público e admin CRUD.

Aplica RGN-T1: nenhuma credencial hardcoded; tudo via os.environ.

Anti-enum (gap #3): /register sempre retorna 201 com mensagem genérica;
verificação de duplicado é INDIRETA (tentar login com a senha nova
falha porque a conta original manteve a senha antiga).
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from docuvector.domain.entities import User


# =============================================================
# Helpers
# =============================================================
def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


# =============================================================
# /auth/register — sempre retorna 201 (anti-enum)
# =============================================================
@pytest.mark.integration
def test_register_returns_201_with_generic_message(
    client: TestClient,
    clean_database: None,
) -> None:
    payload = {
        "email": _make_unique_email(),
        "password": os.environ["TEST_REGISTRATION_PASSWORD"],
    }
    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    # Sem `id` nem `email` no payload (anti-enum).
    assert "id" not in body
    assert "email" not in body
    assert "message" in body


@pytest.mark.integration
def test_register_then_login_succeeds(
    client: TestClient,
    clean_database: None,
) -> None:
    email = _make_unique_email()
    password = os.environ["TEST_REGISTRATION_PASSWORD"]

    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201

    token = _login(client, email, password)
    assert token


@pytest.mark.integration
def test_duplicate_email_returns_201_but_does_not_replace_existing(
    client: TestClient,
    clean_database: None,
) -> None:
    """Duplicado retorna 201 (anti-enum) mas a senha original NÃO muda."""
    email = _make_unique_email()
    original_password = os.environ["TEST_REGISTRATION_PASSWORD"]
    attacker_password = os.environ["TEST_USER_TWO_PASSWORD"]

    first_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": original_password},
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": attacker_password},
    )
    assert second_response.status_code == 201

    # Login só funciona com a senha original.
    valid_token = _login(client, email, original_password)
    assert valid_token

    attacker_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": attacker_password},
    )
    assert attacker_login.status_code == 401


@pytest.mark.integration
def test_register_with_weak_password_returns_422(
    client: TestClient,
    clean_database: None,
) -> None:
    payload = {
        "email": _make_unique_email(),
        "password": os.environ["TEST_WEAK_PASSWORD"],
    }
    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422


# =============================================================
# /admin/users — autorização
# =============================================================
@pytest.mark.integration
def test_regular_user_cannot_list_users(
    client: TestClient,
    regular_user_one: User,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    response = client.get("/api/v1/admin/users", headers=_bearer(token))
    assert response.status_code == 403


@pytest.mark.integration
def test_admin_lists_all_users(
    client: TestClient,
    admin_user: User,
    regular_user_one: User,
    regular_user_two: User,
) -> None:
    admin_token = _login(client, admin_user.email, os.environ["TEST_ADMIN_PASSWORD"])
    response = client.get("/api/v1/admin/users", headers=_bearer(admin_token))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 3


@pytest.mark.integration
def test_admin_creates_new_user_via_endpoint(
    client: TestClient,
    admin_user: User,
) -> None:
    admin_token = _login(client, admin_user.email, os.environ["TEST_ADMIN_PASSWORD"])
    new_email = _make_unique_email()

    response = client.post(
        "/api/v1/admin/users",
        headers=_bearer(admin_token),
        json={
            "email": new_email,
            "password": os.environ["TEST_REGISTRATION_PASSWORD"],
            "role": "user",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == new_email
    assert response.json()["role"] == "user"


@pytest.mark.integration
def test_admin_cannot_delete_self(
    client: TestClient,
    admin_user: User,
) -> None:
    admin_token = _login(client, admin_user.email, os.environ["TEST_ADMIN_PASSWORD"])
    response = client.delete(
        f"/api/v1/admin/users/{admin_user.id}",
        headers=_bearer(admin_token),
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_admin_deletes_regular_user(
    client: TestClient,
    admin_user: User,
    regular_user_one: User,
) -> None:
    admin_token = _login(client, admin_user.email, os.environ["TEST_ADMIN_PASSWORD"])
    response = client.delete(
        f"/api/v1/admin/users/{regular_user_one.id}",
        headers=_bearer(admin_token),
    )
    assert response.status_code == 204


@pytest.mark.integration
def test_admin_promotes_user_to_admin(
    client: TestClient,
    admin_user: User,
    regular_user_one: User,
) -> None:
    admin_token = _login(client, admin_user.email, os.environ["TEST_ADMIN_PASSWORD"])
    response = client.patch(
        f"/api/v1/admin/users/{regular_user_one.id}/role",
        headers=_bearer(admin_token),
        json={"role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
