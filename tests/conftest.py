"""Configuração compartilhada de fixtures para a suite de testes."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

# Variáveis mínimas necessárias para que Settings() valide durante os testes.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_NAME", "DocuVector Lite")
os.environ.setdefault("APP_HOST", "127.0.0.1")
os.environ.setdefault("APP_PORT", "8000")
os.environ.setdefault("LOG_LEVEL", "INFO")

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "docuvector_test")
os.environ.setdefault("POSTGRES_USER", "docuvector_test")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
test_database_url = (
    "postgresql+psycopg://docuvector_test:"
    "test-postgres-password@localhost:5432/docuvector_test"
)  # pragma: allowlist secret

os.environ.setdefault("DATABASE_URL", test_database_url)

os.environ.setdefault("CHROMA_PERSIST_DIR", "./data/test_chroma")

os.environ.setdefault(
    "JWT_SECRET_KEY",
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # pragma: allowlist secret
)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")

os.environ.setdefault("SEED_ADMIN_EMAIL", "admin@docuvector.test")
os.environ.setdefault("SEED_ADMIN_PASSWORD", "admin-test-password")
os.environ.setdefault("SEED_USER1_EMAIL", "user1@docuvector.test")
os.environ.setdefault("SEED_USER1_PASSWORD", "user1-test-password")
os.environ.setdefault("SEED_USER2_EMAIL", "user2@docuvector.test")
os.environ.setdefault("SEED_USER2_PASSWORD", "user2-test-password")

os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
os.environ.setdefault("OPENAI_EMBEDDING_DIMENSIONS", "1536")
os.environ.setdefault("OPENAI_EMBEDDING_COST_PER_MILLION_TOKENS", "0.02")

os.environ.setdefault("SENTENCE_TRANSFORMERS_MODEL", "intfloat/multilingual-e5-small")
os.environ.setdefault("SENTENCE_TRANSFORMERS_DIMENSIONS", "384")
os.environ.setdefault("HF_HOME", "./data/test_hf_cache")

os.environ.setdefault("OPENAI_LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("OPENAI_LLM_TEMPERATURE", "0.2")
os.environ.setdefault("OPENAI_LLM_MAX_TOKENS", "600")

os.environ.setdefault("RAG_CHUNK_SIZE", "1000")
os.environ.setdefault("RAG_CHUNK_OVERLAP", "200")
os.environ.setdefault("RAG_TOP_K", "5")
os.environ.setdefault("RAG_SIMILARITY_THRESHOLD", "0.6")

os.environ.setdefault("UPLOAD_MAX_BYTES", "10485760")
os.environ.setdefault("LOGIN_RATE_LIMIT_PER_MINUTE", "10")

if TYPE_CHECKING:
    from fastapi import FastAPI
# Estes imports precisam ocorrer depois da configuração de variáveis de ambiente
# de teste, porque `get_settings()` lê e valida o ambiente no carregamento da
# aplicação. Em testes, definimos valores seguros e fictícios antes de importar
# `create_app`.
# `noqa: E402` instrui o Ruff a ignorar apenas a regra E402 nesta linha.
# E402 = "module level import not at top of file". Aqui a exceção é intencional
# para preservar a ordem correta de inicialização dos testes.
from docuvector.config.settings import get_settings  # noqa: E402
from docuvector.main import create_app  # noqa: E402


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
