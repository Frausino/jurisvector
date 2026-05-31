"""Teste integration end-to-end do pipeline RAG.

Fluxo coberto:
    upload de TXT  →  ingestão (extract + chunk + embed local + store)
                  →  ask via /api/v1/queries/ask
                  →  resposta com fontes citáveis

Decisões do teste:

1.  **LLM é mockado via `dependency_overrides`**. Chamar OpenAI real
    custa dinheiro, é não-determinístico e exige rede no CI. O mock
    devolve uma string fixa que cita `[1]`.

2.  **Embedder local (E5) é REAL**. É a parte semântica não-trivial
    do pipeline; mockar tira a confiança do teste. E5 small carrega
    rápido (~118MB no primeiro run; cache em `./data/test_hf_cache`).
    Se isso virar lento no CI, marcar com `@pytest.mark.slow` e
    excluir do gate padrão.

3.  **TXT pequeno e jurídico**. Foco no caminho feliz, não em PDF
    complexo. Cobertura de PDF/MD/grandes fica em testes próprios.

4.  **Cleanup do Chroma é manual ao fim**. O store persiste em disco
    entre testes; sem cleanup, runs subsequentes acumulam vetores
    e violam isolamento.
"""

from __future__ import annotations

import io
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from docuvector.api import deps
from docuvector.domain.interfaces.llm_client import LlmCompletion

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from docuvector.domain.entities import User


_LEGAL_DOCUMENT_CONTENT = """
CONTRATO DE PRESTAÇÃO DE SERVIÇOS

CLÁUSULA PRIMEIRA - DO OBJETO
O presente contrato tem por objeto a prestação de serviços de consultoria
jurídica especializada em direito empresarial.

CLÁUSULA SEGUNDA - DO PRAZO
O contrato vigorará pelo prazo de 12 (doze) meses, contados a partir da
data de sua assinatura, podendo ser prorrogado por igual período mediante
acordo expresso entre as partes.

CLÁUSULA TERCEIRA - DA RESCISÃO
O presente contrato poderá ser rescindido por qualquer das partes mediante
notificação prévia por escrito com antecedência mínima de 30 (trinta) dias.
Em caso de descumprimento de qualquer cláusula contratual, a parte
prejudicada poderá rescindir imediatamente o contrato, sem direito a aviso
prévio pela parte infratora.

CLÁUSULA QUARTA - DO VALOR
Pelos serviços prestados, a CONTRATANTE pagará à CONTRATADA o valor mensal
de R$ 5.000,00 (cinco mil reais), até o quinto dia útil de cada mês.
""".strip()


class _DeterministicLlmStub:
    """LLM stub que devolve resposta fixa citando [1]."""

    def complete(self, system_prompt: str, user_prompt: str) -> LlmCompletion:
        return LlmCompletion(
            text=(
                "A rescisão exige notificação prévia por escrito de 30 dias "
                "[1]. Em caso de descumprimento, a rescisão pode ser imediata "
                "[1]."
            ),
            tokens_used=150,
            cost_usd=0.000_07,
            latency_ms=120,
            model="gpt-4o-mini-stub",
        )


# =============================================================
# Fixtures locais ao teste
# =============================================================
@pytest.fixture
def stub_llm_override(application: FastAPI) -> Iterator[None]:
    """Substitui o cliente LLM pelo stub durante este teste."""
    application.dependency_overrides[deps.provide_llm_client] = _DeterministicLlmStub

    yield

    application.dependency_overrides.pop(
        deps.provide_llm_client,
        None,
    )


@pytest.fixture
def clean_chroma_dir() -> Iterator[None]:
    """Garante que cada run começa com Chroma vazio.

    `get_vector_store` é `@lru_cache`; precisamos limpar o cache para
    forçar reabertura quando o diretório é recriado.
    """
    chroma_path = Path(os.environ.get("CHROMA_PERSIST_DIR", "./data/test_chroma"))
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)
    chroma_path.mkdir(parents=True, exist_ok=True)

    deps.get_vector_store.cache_clear()
    yield
    deps.get_vector_store.cache_clear()
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)


def _login(test_client: TestClient, email: str, password: str) -> str:
    response = test_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# =============================================================
# Teste end-to-end
# =============================================================
@pytest.mark.integration
@pytest.mark.slow
def test_upload_then_ask_returns_answer_with_sources(
    client: TestClient,
    regular_user_one: User,
    stub_llm_override: None,
    clean_chroma_dir: None,
) -> None:
    """upload → ask → resposta com >= 1 fonte e grounded=True."""
    token = _login(
        client,
        regular_user_one.email,
        os.environ["TEST_USER_ONE_PASSWORD"],
    )

    # 1) Upload de contrato em TXT.
    upload_response = client.post(
        "/api/v1/documents",
        headers=_bearer(token),
        files={
            "file": (
                "contrato_servicos.txt",
                io.BytesIO(_LEGAL_DOCUMENT_CONTENT.encode("utf-8")),
                "text/plain",
            ),
        },
        data={"embedding_provider": "sentence_transformers"},
    )
    assert upload_response.status_code == 201, upload_response.text
    upload_body = upload_response.json()
    assert upload_body["chunks_created"] >= 1
    assert upload_body["document"]["status"] == "embedded"

    # 2) Pergunta sobre o conteúdo.
    ask_response = client.post(
        "/api/v1/queries/ask",
        headers=_bearer(token),
        json={
            "query": "Qual o prazo de notificação prévia para rescisão do contrato?",
            "embedding_provider": "sentence_transformers",
        },
    )
    assert ask_response.status_code == 200, ask_response.text

    ask_body = ask_response.json()
    assert ask_body["grounded"] is True
    assert len(ask_body["sources"]) >= 1
    assert ask_body["sources"][0]["citation_number"] == 1
    assert ask_body["sources"][0]["document_filename"] == "contrato_servicos.txt"
    assert "rescisão" in ask_body["answer"].casefold()
    assert ask_body["tokens_used"] == 150
    assert ask_body["model"] == "gpt-4o-mini-stub"


@pytest.mark.integration
def test_ask_without_token_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/queries/ask",
        json={"query": "qualquer pergunta sem auth"},
    )
    assert response.status_code == 401


@pytest.mark.integration
def test_ask_with_too_short_query_returns_422(
    client: TestClient,
    regular_user_one: User,
) -> None:
    token = _login(
        client,
        regular_user_one.email,
        os.environ["TEST_USER_ONE_PASSWORD"],
    )

    response = client.post(
        "/api/v1/queries/ask",
        headers=_bearer(token),
        json={"query": "ab"},
    )
    assert response.status_code == 422
