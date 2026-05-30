"""Configuração compartilhada de fixtures para a suíte de testes.

Decisões arquiteturais documentadas neste módulo:

1.  **Banco compartilhado com desenvolvimento.** Testes de integração usam
    o mesmo banco do dev (`docuvector`), isolando estado entre testes via
    `TRUNCATE`. Em produção haveria banco `_test` dedicado.

2.  **Imports lazy nas fixtures.** O `_set_test_environment()` precisa
    executar ANTES de qualquer import de `docuvector`, porque o `Settings`
    valida variáveis de ambiente no momento da importação.

3.  **`127.0.0.1` em vez de `localhost`.** No Windows, psycopg resolve
    `localhost` primeiro como IPv6. Forçar `127.0.0.1` elimina timeout.

4.  **`bcrypt` com `rounds=4` em teste.** Cost mínimo aceito pelo
    Settings (`ge=4`). Produção usa 12 (OWASP).

5.  **RGN-T1 — Credenciais NUNCA hardcoded.** Toda senha vem de
    `os.environ` via `setdefault`. Inclui:
        TEST_ADMIN_PASSWORD
        TEST_USER_ONE_PASSWORD
        TEST_USER_TWO_PASSWORD
        TEST_REGISTRATION_PASSWORD  (forte; passa NIST)
        TEST_WEAK_PASSWORD          (curta; FALHA na NIST)
    Os defaults aqui são para CI sem `.env`; um `.env` pode sobrepor.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from fastapi import FastAPI

    from docuvector.domain.entities import User


# =============================================================
# Bootstrap de ambiente
# =============================================================
def _set_test_environment() -> None:
    """Popula `os.environ` com defaults mínimos para a aplicação subir."""
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("APP_HOST", "127.0.0.1")
    os.environ.setdefault("APP_PORT", "8000")
    os.environ.setdefault("LOG_LEVEL", "INFO")

    os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "docuvector")
    os.environ.setdefault("POSTGRES_USER", "docuvector_app")
    os.environ.setdefault(
        "POSTGRES_PASSWORD",
        "docuvector_dev_password",  # pragma: allowlist secret
    )
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://docuvector_app:docuvector_dev_password"  # pragma: allowlist secret
        "@127.0.0.1:5432/docuvector",
    )

    jwt_test_secret = "".join(["0123456789abcdef"] * 4)
    os.environ.setdefault("JWT_SECRET_KEY", jwt_test_secret)
    os.environ.setdefault("JWT_ALGORITHM", "HS256")
    os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")

    # Bootstrap admin (substitui antigos SEED_USER1/2).
    os.environ.setdefault("SEED_ADMIN_EMAIL", "admin@docuvector.com")
    os.environ.setdefault("SEED_ADMIN_PASSWORD", "admin-test-bootstrap-pw")

    # Credenciais ESPECÍFICAS para fixtures de teste. RGN-T1 aplicada:
    # nenhum teste cita senhas literalmente; tudo passa por aqui.
    os.environ.setdefault("TEST_ADMIN_PASSWORD", "admin-test-bootstrap-pw")
    os.environ.setdefault("TEST_USER_ONE_PASSWORD", "user-one-strong-password")
    os.environ.setdefault("TEST_USER_TWO_PASSWORD", "user-two-strong-password")
    os.environ.setdefault("TEST_REGISTRATION_PASSWORD", "registration-strong-pwd")
    os.environ.setdefault("TEST_WEAK_PASSWORD", "short")

    os.environ.setdefault("OPENAI_API_KEY", "")
    os.environ.setdefault("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    os.environ.setdefault("OPENAI_EMBEDDING_DIMENSIONS", "1536")
    os.environ.setdefault("OPENAI_EMBEDDING_COST_PER_MILLION_TOKENS", "0.02")

    os.environ.setdefault("SENTENCE_TRANSFORMERS_MODEL", "intfloat/multilingual-e5-small")
    os.environ.setdefault("SENTENCE_TRANSFORMERS_DIMENSIONS", "384")
    os.environ.setdefault("HF_HOME", "./data/test_hf_cache")
    os.environ.setdefault("CHROMA_PERSIST_DIR", "./data/test_chroma")

    os.environ.setdefault("OPENAI_LLM_MODEL", "gpt-4o-mini")
    os.environ.setdefault("OPENAI_LLM_TEMPERATURE", "0.2")
    os.environ.setdefault("OPENAI_LLM_MAX_TOKENS", "600")

    os.environ.setdefault("RAG_CHUNK_SIZE", "1000")
    os.environ.setdefault("RAG_CHUNK_OVERLAP", "200")
    os.environ.setdefault("RAG_TOP_K", "5")
    os.environ.setdefault("RAG_SIMILARITY_THRESHOLD", "0.6")

    os.environ.setdefault("UPLOAD_MAX_BYTES", "10485760")
    os.environ.setdefault("LOGIN_RATE_LIMIT_PER_MINUTE", "10000")
    os.environ.setdefault("REGISTER_RATE_LIMIT_PER_MINUTE", "10000")

    os.environ.setdefault("PASSWORD_MIN_LENGTH", "12")
    os.environ.setdefault("BCRYPT_ROUNDS", "4")

    _force_ipv4_in_database_url()


def _force_ipv4_in_database_url() -> None:
    """Substitui `localhost` por `127.0.0.1` na `DATABASE_URL` corrente."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "localhost" in database_url:
        os.environ["DATABASE_URL"] = database_url.replace("localhost", "127.0.0.1")


_set_test_environment()


# =============================================================
# Fixtures de aplicação (escopo de sessão)
#
# Imports lazy intencionais: garantem que _set_test_environment() já
# rodou antes que qualquer módulo do projeto seja importado.
# =============================================================
@pytest.fixture(scope="session")
def application() -> FastAPI:
    from docuvector.config.settings import get_settings
    from docuvector.main import create_app

    get_settings.cache_clear()
    return create_app()


@pytest.fixture(scope="session")
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as test_client:
        yield test_client


# =============================================================
# Fixtures de banco
# =============================================================
@pytest.fixture
def db_session() -> Iterator[Session]:
    from docuvector.infrastructure.persistence.database import get_session_factory

    session_factory = get_session_factory()
    with session_factory() as session:
        yield session


@pytest.fixture
def clean_database() -> Iterator[None]:
    from docuvector.infrastructure.persistence.database import get_session_factory

    session_factory = get_session_factory()
    with session_factory() as cleanup_session:
        cleanup_session.execute(text("TRUNCATE TABLE audit_logs CASCADE"))
        cleanup_session.execute(text("TRUNCATE TABLE documents CASCADE"))
        cleanup_session.execute(text("TRUNCATE TABLE users CASCADE"))
        cleanup_session.commit()

    yield


# =============================================================
# Fixtures de usuário (criados via repositório direto, não API)
# =============================================================
@pytest.fixture
def admin_user(clean_database: None) -> User:
    return _create_user(
        email="admin@test.com",
        plain_password=os.environ["TEST_ADMIN_PASSWORD"],
        is_admin=True,
    )


@pytest.fixture
def regular_user_one(clean_database: None) -> User:
    return _create_user(
        email="user1@test.com",
        plain_password=os.environ["TEST_USER_ONE_PASSWORD"],
        is_admin=False,
    )


@pytest.fixture
def regular_user_two(clean_database: None) -> User:
    return _create_user(
        email="user2@test.com",
        plain_password=os.environ["TEST_USER_TWO_PASSWORD"],
        is_admin=False,
    )


def _create_user(email: str, plain_password: str, *, is_admin: bool) -> User:
    """Persiste um usuário diretamente no banco (bypassa a API).

    O objetivo das fixtures de usuário é arranjar estado, não testar o
    fluxo de criação. `rounds=4` no bcrypt mantém fixtures rápidas.
    """
    from docuvector.domain.entities import User
    from docuvector.domain.enums import UserRole
    from docuvector.infrastructure.persistence.database import get_session_factory
    from docuvector.infrastructure.persistence.user_repository_impl import (
        SqlAlchemyUserRepository,
    )
    from docuvector.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher

    session_factory = get_session_factory()
    hasher = BcryptPasswordHasher(rounds=4)

    with session_factory() as session:
        user_repository = SqlAlchemyUserRepository(session)
        user_to_persist = User(
            email=email,
            password_hash=hasher.hash(plain_password),
            role=UserRole.ADMIN if is_admin else UserRole.USER,
        )
        persisted = user_repository.save(user_to_persist)
        session.commit()
        return persisted
