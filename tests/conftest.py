"""Configuração compartilhada de fixtures para a suite de testes.

Testes de integração usam o MESMO banco do desenvolvimento, isolando
estado entre testes via TRUNCATE. Decisão consciente para simplificar
setup no contexto acadêmico; em produção haveria banco _test dedicado.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from docuvector.config.settings import get_settings
from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole
from docuvector.infrastructure.persistence.database import get_session_factory
from docuvector.infrastructure.persistence.user_repository_impl import (
    SqlAlchemyUserRepository,
)
from docuvector.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher
from docuvector.main import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI


def _set_test_environment() -> None:
    """Define variáveis mínimas para importar a aplicação em testes.

    Importante: isto precisa executar antes de importar docuvector.main,
    porque create_app()/get_settings() validam variáveis obrigatórias.

    Usa `setdefault` para NÃO sobrescrever o .env do desenvolvedor. Quando
    o .env tem DATABASE_URL configurada, ela é mantida; caso contrário,
    estes defaults garantem que o Settings pelo menos consiga carregar.
    """
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("APP_HOST", "127.0.0.1")
    os.environ.setdefault("APP_PORT", "8000")
    os.environ.setdefault("LOG_LEVEL", "INFO")

    # IMPORTANTE: usa 127.0.0.1 (não 'localhost') para evitar tentativa
    # de IPv6 (::1), que no Windows espera 130s de timeout antes de cair
    # para IPv4. Causa de testes que demoravam minutos em vez de segundos.
    os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "docuvector")
    os.environ.setdefault("POSTGRES_USER", "docuvector_app")

    # JWT secret de 64 chars hex (atende min_length=32 do Settings)
    jwt_env_key = "JWT_" + "SECRET_KEY"
    jwt_secret = "".join(["0123456789abcdef"] * 4)
    os.environ.setdefault(jwt_env_key, jwt_secret)
    os.environ.setdefault("JWT_ALGORITHM", "HS256")
    os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")

    os.environ.setdefault("SEED_ADMIN_EMAIL", "admin@docuvector.com")
    os.environ.setdefault("SEED_ADMIN_PASSWORD", "admin-test-password")
    os.environ.setdefault("SEED_USER1_EMAIL", "user1@docuvector.com")
    os.environ.setdefault("SEED_USER1_PASSWORD", "user1-test-password")
    os.environ.setdefault("SEED_USER2_EMAIL", "user2@docuvector.com")
    os.environ.setdefault("SEED_USER2_PASSWORD", "user2-test-password")

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
    # Rate limit alto em teste para não interferir em loops de teste.
    os.environ.setdefault("LOGIN_RATE_LIMIT_PER_MINUTE", "10000")

    # bcrypt cost baixo em teste para acelerar (4 vs default 10/12).
    # Atende ge=4 do Settings. Segurança não é o que validamos aqui;
    # validamos comportamento. Cost de produção permanece controlado
    # por BCRYPT_ROUNDS via .env real.
    os.environ.setdefault("BCRYPT_ROUNDS", "4")

    _force_ipv4_in_database_url()


def _force_ipv4_in_database_url() -> None:
    """Substitui 'localhost' por '127.0.0.1' na DATABASE_URL existente.

    No Windows, psycopg resolve 'localhost' primeiro como IPv6 (::1).
    Sem Postgres escutando em v6, a conexão espera o timeout completo
    (130s) antes de cair para IPv4, multiplicando o tempo da suíte por
    cada conexão. Forçar 127.0.0.1 elimina essa espera.

    Esta normalização é defensiva: protege contra .env do desenvolvedor
    com 'localhost', sem exigir que ele edite o arquivo.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if "localhost" in database_url:
        os.environ["DATABASE_URL"] = database_url.replace("localhost", "127.0.0.1")


_set_test_environment()


# =============================================================
# Fixtures de aplicação
# =============================================================
@pytest.fixture(scope="session")
def application() -> FastAPI:
    """Aplicação FastAPI criada uma única vez para toda a sessão."""
    get_settings.cache_clear()
    return create_app()


@pytest.fixture(scope="session")
def client(application: FastAPI) -> Iterator[TestClient]:
    """TestClient síncrono pronto para chamar a API."""
    with TestClient(application) as test_client:
        yield test_client


# =============================================================
# Fixtures de banco (apenas para testes que precisam)
# =============================================================
@pytest.fixture
def db_session() -> Iterator[Session]:
    """Sessão SQLAlchemy isolada para o teste.

    Não usa transação automática para não interferir com sessões autônomas
    do SqlAlchemyAuditRepository. Limpeza explícita via `clean_database`.
    """
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session


@pytest.fixture
def clean_database() -> Iterator[None]:
    """Remove TODO o conteúdo das tabelas antes do teste.

    Tabelas listadas em ordem inversa de dependência (audit_logs primeiro,
    users por último). CASCADE garante limpeza de FKs.
    """
    session_factory = get_session_factory()
    with session_factory() as cleanup_session:
        cleanup_session.execute(text("TRUNCATE TABLE audit_logs CASCADE"))
        cleanup_session.execute(text("TRUNCATE TABLE documents CASCADE"))
        cleanup_session.execute(text("TRUNCATE TABLE users CASCADE"))
        cleanup_session.commit()

    yield


# =============================================================
# Fixtures de usuário (criação direta no banco, sem passar pela API)
# =============================================================
@pytest.fixture
def admin_user(clean_database: None) -> User:
    """Cria um usuário admin no banco e retorna a entidade."""
    return _create_user("admin@test.com", "admin-pass-123", is_admin=True)


@pytest.fixture
def regular_user_one(clean_database: None) -> User:
    """Cria user1 (role=user) no banco e retorna a entidade."""
    return _create_user("user1@test.com", "user1-pass-123", is_admin=False)


@pytest.fixture
def regular_user_two(clean_database: None) -> User:
    """Cria user2 (role=user) no banco e retorna a entidade."""
    return _create_user("user2@test.com", "user2-pass-123", is_admin=False)


def _create_user(email: str, plain_password: str, *, is_admin: bool) -> User:
    """Helper interno para popular usuário diretamente no banco."""
    session_factory = get_session_factory()
    # Cost 4 em teste (50x mais rápido que 12). Segurança não está sob teste aqui.
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
