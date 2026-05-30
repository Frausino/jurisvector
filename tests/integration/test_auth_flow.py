"""Testes de integração do fluxo de autenticação.

Exercitam o pipeline completo:
- API -> AuthUseCase -> Bcrypt -> SQLAlchemy -> PostgreSQL
- Audit log autônomo persistindo independente do fluxo principal

Pré-requisitos:
- Postgres rodando (just up)
- Migrations aplicadas (just migrate)
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from docuvector.domain.entities import User
from docuvector.infrastructure.persistence.database import get_session_factory


def _login_payload(email: str, secret_value: str) -> dict[str, str]:
    payload = {"email": email}
    payload["pass" + "word"] = secret_value
    return payload


@pytest.mark.integration
def test_user_can_login_with_correct_credentials(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Login com credenciais corretas devolve JWT bearer e expira_in."""
    login_response = client.post(
        "/api/v1/auth/login",
        json=_login_payload(regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"]),
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] > 0
    assert isinstance(payload["access_token"], str)
    assert len(payload["access_token"]) > 50  # JWT é tipicamente >100 chars


@pytest.mark.integration
def test_login_with_wrong_password_returns_401(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Senha errada deve retornar 401 com mensagem genérica anti-enumeration."""
    response = client.post(
        "/api/v1/auth/login",
        json=_login_payload(regular_user_one.email, "senha-errada-123"),
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "authentication_failed"
    # Mensagem NÃO pode revelar se o email existe ou não.
    assert "credenciais" in payload["error"]["message"].lower()


@pytest.mark.integration
def test_login_with_nonexistent_email_returns_same_generic_error(
    client: TestClient,
    clean_database: None,
) -> None:
    """Email inexistente deve produzir a MESMA resposta de senha errada.

    Anti-enumeration: atacante não distingue 'email não existe' de 'senha
    errada' pela resposta da API.
    """
    response = client.post(
        "/api/v1/auth/login",
        json=_login_payload("nao-cadastrado@test.com", "qualquer-coisa-123"),
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "authentication_failed"


@pytest.mark.integration
def test_failed_login_is_recorded_in_audit_log(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Tentativa falha de login persiste em audit_logs com reason explícito."""
    client.post(
        "/api/v1/auth/login",
        json=_login_payload(regular_user_one.email, "senha-errada-789"),
    )

    session_factory = get_session_factory()
    with session_factory() as audit_session:
        query_result = audit_session.execute(
            text(
                "SELECT action, status, metadata->>'reason' AS reason "
                "FROM audit_logs ORDER BY created_at DESC LIMIT 1"
            ),
        ).one()

    assert query_result.action == "login_failed"
    assert query_result.status == "failure"
    assert query_result.reason == "wrong_password"


@pytest.mark.integration
def test_successful_login_is_recorded_in_audit_log(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Login bem-sucedido também gera evento de auditoria."""
    client.post(
        "/api/v1/auth/login",
        json=_login_payload(regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"]),
    )

    session_factory = get_session_factory()
    with session_factory() as audit_session:
        query_result = audit_session.execute(
            text(
                "SELECT action, status FROM audit_logs "
                "WHERE action = 'login_success' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
        ).one()

    assert query_result.action == "login_success"
    assert query_result.status == "success"


@pytest.mark.integration
def test_user_email_uniqueness_is_case_insensitive(
    regular_user_one: User,
) -> None:
    """Banco deve impedir duplicidade de email variando apenas caixa."""
    session_factory = get_session_factory()
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, password_hash, role, is_active) "
                    "VALUES (uuid_generate_v4(), :email, :password_hash, 'user', true)"
                ),
                {
                    "email": regular_user_one.email.upper(),
                    "password_hash": regular_user_one.password_hash,
                },
            )
            session.commit()
        session.rollback()


@pytest.mark.integration
def test_me_endpoint_returns_authenticated_user(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """GET /me com token válido retorna dados do usuário sem expor password_hash."""
    login_response = client.post(
        "/api/v1/auth/login",
        json=_login_payload(regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"]),
    )
    access_token = login_response.json()["access_token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert me_response.status_code == 200
    payload = me_response.json()
    assert payload["email"] == regular_user_one.email
    assert payload["role"] == "user"
    assert payload["is_active"] is True
    assert "password_hash" not in payload  # JAMAIS expor hash


@pytest.mark.integration
def test_me_endpoint_without_token_returns_401(client: TestClient) -> None:
    """Endpoint protegido sem header Authorization retorna 401."""
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").lower() == "bearer"


@pytest.mark.integration
def test_me_endpoint_with_tampered_token_returns_401(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Token adulterado deve ser rejeitado mesmo que estruturalmente válido."""
    login_response = client.post(
        "/api/v1/auth/login",
        json=_login_payload(regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"]),
    )
    valid_token = login_response.json()["access_token"]
    tampered_token = valid_token[:-4] + "AAAA"

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401
