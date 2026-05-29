"""Configuração compartilhada de fixtures para a suíte de testes.

Decisões arquiteturais documentadas neste módulo:

1.  **Banco compartilhado com desenvolvimento.** Testes de integração usam
    o mesmo banco do dev (`docuvector`), isolando estado entre testes via
    `TRUNCATE`. Em produção haveria banco `_test` dedicado; aqui é uma
    simplificação consciente para o contexto acadêmico.

2.  **Imports lazy nas fixtures.** O `_set_test_environment()` precisa
    executar ANTES de qualquer import de `docuvector`, porque o `Settings`
    valida variáveis de ambiente no momento da importação. Importar
    `docuvector.main` no topo do módulo quebraria essa ordem.

3.  **`127.0.0.1` em vez de `localhost`.** No Windows, `psycopg` resolve
    `localhost` primeiro como IPv6 (`::1`). Sem Postgres escutando em v6,
    cada conexão espera o timeout de 130s antes de cair para IPv4. Forçar
    `127.0.0.1` elimina essa latência (suíte caiu de 13min para ~35s).

4.  **`bcrypt` com `rounds=4` em teste.** Cost mínimo aceito pelo Settings
    (`ge=4`). Segurança real não está sob teste aqui; está sob teste o
    comportamento do fluxo. Produção usa cost 12 (OWASP), controlado por
    `BCRYPT_ROUNDS` no `.env` real.

5.  **Configuração de banco vem do `.env` local ou do runner de CI.**
    A suíte não inventa credenciais próprias. Este módulo carrega o `.env`
    da raiz do projeto quando ele existe e, na ausência dele, espera que o
    runner de CI injete as mesmas variáveis. A fonte de verdade permanece
    fora do código.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
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
def _load_local_dotenv() -> None:
    """Carrega `.env` da raiz do repositório sem sobrescrever o ambiente atual.

    A prioridade é:
    1. variáveis já presentes no ambiente externo (CI/shell);
    2. variáveis declaradas no `.env` local;
    3. defaults de teste apenas para parâmetros não sensíveis.
    """
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.is_file():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _set_test_environment() -> None:
    """Popula `os.environ` com defaults mínimos para a aplicação subir.

    Usa `setdefault` para NÃO sobrescrever o `.env` do desenvolvedor.
    Quando o `.env` já define a variável, ela vence; estes valores só
    entram em CI sem `.env` ou em primeira execução local.
    """
    _load_local_dotenv()

    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("APP_HOST", "127.0.0.1")
    os.environ.setdefault("APP_PORT", "8000")
    os.environ.setdefault("LOG_LEVEL", "INFO")

    # JWT secret de 64 chars hex (atende min_length=32 do Settings).
    # Concatenado em runtime para evitar match heurístico do detect-secrets.
    jwt_test_secret = "".join(["0123456789abcdef"] * 4)
    os.environ.setdefault("JWT_SECRET_KEY", jwt_test_secret)
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

    # Cost mínimo do bcrypt em teste (ge=4 do Settings). Produção controla
    # via BCRYPT_ROUNDS no .env real (12 default).
    os.environ.setdefault("BCRYPT_ROUNDS", "4")

    # =============================================================
    # Database defaults
    # =============================================================
    os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "docuvector")
    os.environ.setdefault("POSTGRES_USER", "docuvector_app")
    os.environ.setdefault(
        "POSTGRES_PASSWORD",
        "trocar_por_senha_forte_local",
    )

    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = (
            "postgresql+psycopg://"
            f"{os.environ['POSTGRES_USER']}:"
            f"{os.environ['POSTGRES_PASSWORD']}@"
            f"{os.environ['POSTGRES_HOST']}:"
            f"{os.environ['POSTGRES_PORT']}/"
            f"{os.environ['POSTGRES_DB']}"
        )

        _force_ipv4_in_database_url()


def _force_ipv4_in_database_url() -> None:
    """Substitui `localhost` por `127.0.0.1` na `DATABASE_URL` corrente.

    Normalização defensiva: protege contra `.env` do desenvolvedor com
    `localhost`, sem exigir que ele edite o arquivo. Ver decisão arq. (3)
    no docstring do módulo.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if "localhost" in database_url:
        os.environ["DATABASE_URL"] = database_url.replace("localhost", "127.0.0.1")


_set_test_environment()


# =============================================================
# Fixtures de aplicação (escopo de sessão, custosas)
#
# As fixtures abaixo usam imports lazy intencionalmente, para garantir
# que _set_test_environment() já tenha rodado antes que qualquer módulo
# do projeto seja importado. Ver decisão arquitetural (2) no docstring.
# =============================================================
@pytest.fixture(scope="session")
def application() -> FastAPI:
    """Aplicação FastAPI construída uma única vez para toda a sessão."""
    from docuvector.config.settings import get_settings
    from docuvector.main import create_app

    get_settings.cache_clear()
    return create_app()


@pytest.fixture(scope="session")
def client(application: FastAPI) -> Iterator[TestClient]:
    """`TestClient` síncrono pronto para chamar a API."""
    with TestClient(application) as test_client:
        yield test_client


# =============================================================
# Fixtures de banco
# =============================================================
@pytest.fixture
def db_session() -> Iterator[Session]:
    """Sessão SQLAlchemy isolada para uso direto no teste.

    Não usa transação automática para não interferir com sessões autônomas
    do `SqlAlchemyAuditRepository`. Limpeza explícita via `clean_database`.
    """
    from docuvector.infrastructure.persistence.database import get_session_factory

    session_factory = get_session_factory()
    with session_factory() as session:
        yield session


@pytest.fixture
def clean_database() -> Iterator[None]:
    """Trunca tabelas antes do teste para isolamento total.

    Ordem inversa de dependência (audit_logs primeiro, users por último).
    `CASCADE` garante limpeza de FKs.
    """
    from docuvector.infrastructure.persistence.database import get_session_factory

    session_factory = get_session_factory()
    with session_factory() as cleanup_session:
        cleanup_session.execute(text("TRUNCATE TABLE audit_logs CASCADE"))
        cleanup_session.execute(text("TRUNCATE TABLE documents CASCADE"))
        cleanup_session.execute(text("TRUNCATE TABLE users CASCADE"))
        cleanup_session.commit()

    yield


# =============================================================
# Fixtures de usuário (criadas direto no banco, sem passar pela API)
# =============================================================
@pytest.fixture
def admin_user(clean_database: None) -> User:
    """Usuário com papel `admin` recém-criado no banco."""
    return _create_user("admin@test.com", "admin-pass-123", is_admin=True)


@pytest.fixture
def regular_user_one(clean_database: None) -> User:
    """Usuário comum (`user`) recém-criado no banco."""
    return _create_user("user1@test.com", "user1-pass-123", is_admin=False)


@pytest.fixture
def regular_user_two(clean_database: None) -> User:
    """Segundo usuário comum, usado em testes de isolamento multi-tenant."""
    return _create_user("user2@test.com", "user2-pass-123", is_admin=False)


def _create_user(email: str, plain_password: str, *, is_admin: bool) -> User:
    """Persiste um usuário diretamente no banco e devolve a entidade.

    Bypassa a API porque o objetivo das fixtures de usuário é arranjar
    estado, não testar o fluxo de criação. Usa `rounds=4` no bcrypt para
    fixtures rápidas, conforme decisão arq. (4).
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
