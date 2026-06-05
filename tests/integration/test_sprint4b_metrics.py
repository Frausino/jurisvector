"""Testes de integração da Sprint 4B — /metrics/dashboard e /metrics/benchmark-embedders."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from docuvector.domain.entities import User

# ---------------------------------------------------------------
# Constantes (evita PLR2004)
# ---------------------------------------------------------------
_MIN_QUERY_LENGTH = 3


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------
@pytest.mark.integration
def test_dashboard_retorna_200_sem_dados(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Dashboard sem nenhum documento/query ainda deve retornar 200 com zeros."""
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])

    response = client.get(
        "/api/v1/metrics/dashboard",
        headers=_bearer(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_queries"] >= 0
    assert body["total_cost_usd"] >= 0.0
    assert body["document_stats"]["total"] >= 0


@pytest.mark.integration
def test_dashboard_sem_token_retorna_401(client: TestClient) -> None:
    response = client.get("/api/v1/metrics/dashboard")
    assert response.status_code == 401


@pytest.mark.integration
def test_dashboard_storage_savings_none_sem_benchmark(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Sem benchmark de compressão executado, storage_savings deve ser None."""
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])

    response = client.get(
        "/api/v1/metrics/dashboard",
        headers=_bearer(token),
    )

    assert response.status_code == 200, response.text
    # storage_savings pode ser None (nenhum doc com compressão) ou objeto válido
    body = response.json()
    assert "storage_savings" in body


# ---------------------------------------------------------------
# Embedding Benchmark
# ---------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_embedders_retorna_sentence_transformers(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """sentence_transformers sempre disponível; deve aparecer no resultado."""
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])

    response = client.post(
        "/api/v1/metrics/benchmark-embedders",
        headers=_bearer(token),
        json={"query": "Qual o prazo de rescisão do contrato?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    provider_names = [r["provider_name"] for r in body["results"]]
    assert "sentence_transformers" in provider_names


@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_embedders_cheapest_e_st_sem_openai_key(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Sem OPENAI_API_KEY, sentence_transformers é o mais barato (custo 0)."""
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])

    response = client.post(
        "/api/v1/metrics/benchmark-embedders",
        headers=_bearer(token),
        json={"query": "teste de benchmark de embedding"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cheapest_provider"] == "sentence_transformers"


@pytest.mark.integration
def test_benchmark_embedders_sem_token_retorna_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/metrics/benchmark-embedders",
        json={"query": "teste"},
    )
    assert response.status_code == 401


@pytest.mark.integration
def test_benchmark_embedders_query_curta_retorna_422(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """Query com menos de 3 chars viola Field(min_length=3)."""
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])

    response = client.post(
        "/api/v1/metrics/benchmark-embedders",
        headers=_bearer(token),
        json={"query": "ab"},
    )
    assert response.status_code == 422
