"""Teste de integração — POST /api/v1/documents/{id}/benchmark-compression.

Fluxo:
    1. Login do usuário regular
    2. Upload de TXT jurídico (embedding local E5 — REAL, não mockado)
    3. POST /{id}/benchmark-compression
    4. Valida payload: 4 compressores, ordenação, savings_pct > 0
    5. BOLA: usuário 2 recebe 404 ao tentar benchmark no doc do usuário 1

Decisões do teste:
    - Embedder local (E5) é REAL. Mockar tiraria a confiança do pipeline.
    - Chroma é limpo antes e depois de cada teste (fixture clean_chroma_dir).
    - Magic numbers viram constantes nomeadas (PLR2004).
    - Sem *args/**kwargs em nenhum fake (não há fakes aqui; usa app real).
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
from docuvector.domain.enums import CompressionMethod

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from docuvector.domain.entities import User

# ---------------------------------------------------------------
# Constantes (evita PLR2004)
# ---------------------------------------------------------------
_EXPECTED_COMPRESSOR_COUNT = 4
_MIN_SAVINGS_PCT = 0.0
_MIN_TARGET_DIM = 2
_INVALID_TARGET_DIM = 1  # viola Field(ge=2)

_LEGAL_DOCUMENT_CONTENT = """
CONTRATO DE PRESTAÇÃO DE SERVIÇOS

CLÁUSULA PRIMEIRA - DO OBJETO
O presente contrato tem por objeto a prestação de serviços de consultoria
jurídica especializada em direito empresarial, compreendendo análise
contratual, pareceres e representação extrajudicial.

CLÁUSULA SEGUNDA - DO PRAZO
O contrato vigorará pelo prazo de 12 (doze) meses, contados da assinatura,
podendo ser prorrogado por igual período mediante acordo entre as partes.

CLÁUSULA TERCEIRA - DA RESCISÃO
O presente contrato poderá ser rescindido por qualquer das partes mediante
notificação prévia por escrito com antecedência mínima de 30 (trinta) dias.
Em caso de descumprimento, a parte prejudicada poderá rescindir de imediato.

CLÁUSULA QUARTA - DO VALOR
A CONTRATANTE pagará à CONTRATADA R$ 5.000,00 mensais até o quinto dia útil.

CLÁUSULA QUINTA - DA CONFIDENCIALIDADE
As partes obrigam-se a manter sigilo absoluto sobre as informações trocadas
em razão deste contrato, sob pena de responder por perdas e danos.
""".strip()


# ---------------------------------------------------------------
# Fixtures locais
# ---------------------------------------------------------------
@pytest.fixture
def clean_chroma_dir() -> Iterator[None]:
    """Isola cada teste com um Chroma vazio. Padrão do projeto."""
    chroma_path = Path(os.environ.get("CHROMA_PERSIST_DIR", "./data/test_chroma"))
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)
    chroma_path.mkdir(parents=True, exist_ok=True)
    deps.get_vector_store.cache_clear()
    yield
    deps.get_vector_store.cache_clear()
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload_contract(client: TestClient, token: str) -> str:
    """Faz upload do contrato de teste; devolve o document_id."""
    response = client.post(
        "/api/v1/documents",
        headers=_bearer(token),
        files={
            "file": (
                "contrato_benchmark.txt",
                io.BytesIO(_LEGAL_DOCUMENT_CONTENT.encode("utf-8")),
                "text/plain",
            )
        },
        data={"embedding_provider": "sentence_transformers"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document"]["status"] == "embedded"
    return str(body["document"]["id"])


# ---------------------------------------------------------------
# Testes de fluxo feliz
# ---------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_retorna_quatro_compressores(
    client: TestClient,
    regular_user_one: User,
    clean_chroma_dir: None,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    doc_id = _upload_contract(client, token)

    response = client.post(
        f"/api/v1/documents/{doc_id}/benchmark-compression",
        headers=_bearer(token),
        json={},
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == _EXPECTED_COMPRESSOR_COUNT


@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_resultados_ordenados_por_retention_desc(
    client: TestClient,
    regular_user_one: User,
    clean_chroma_dir: None,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    doc_id = _upload_contract(client, token)

    response = client.post(
        f"/api/v1/documents/{doc_id}/benchmark-compression",
        headers=_bearer(token),
        json={},
    )

    assert response.status_code == 200, response.text
    retentions = [r["semantic_retention"] for r in response.json()["results"]]
    assert retentions == sorted(retentions, reverse=True)


@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_savings_pct_positivo(
    client: TestClient,
    regular_user_one: User,
    clean_chroma_dir: None,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    doc_id = _upload_contract(client, token)

    response = client.post(
        f"/api/v1/documents/{doc_id}/benchmark-compression",
        headers=_bearer(token),
        json={},
    )

    assert response.status_code == 200, response.text
    assert response.json()["savings_pct"] > _MIN_SAVINGS_PCT


@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_best_method_valido(
    client: TestClient,
    regular_user_one: User,
    clean_chroma_dir: None,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    doc_id = _upload_contract(client, token)

    response = client.post(
        f"/api/v1/documents/{doc_id}/benchmark-compression",
        headers=_bearer(token),
        json={},
    )

    assert response.status_code == 200, response.text
    valid_methods = {m.value for m in CompressionMethod}
    assert response.json()["best_method"] in valid_methods


@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_retention_em_range_valido(
    client: TestClient,
    regular_user_one: User,
    clean_chroma_dir: None,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    doc_id = _upload_contract(client, token)

    response = client.post(
        f"/api/v1/documents/{doc_id}/benchmark-compression",
        headers=_bearer(token),
        json={},
    )

    assert response.status_code == 200, response.text
    for item in response.json()["results"]:
        assert 0.0 <= item["semantic_retention"] <= 1.0


# ---------------------------------------------------------------
# Testes de segurança
# ---------------------------------------------------------------
@pytest.mark.integration
def test_benchmark_sem_token_retorna_401(client: TestClient) -> None:
    nil_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.post(
        f"/api/v1/documents/{nil_uuid}/benchmark-compression",
        json={},
    )
    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.slow
def test_benchmark_bola_usuario_dois_recebe_404(
    client: TestClient,
    regular_user_one: User,
    regular_user_two: User,
    clean_chroma_dir: None,
) -> None:
    """BOLA: usuário 2 não deve acessar doc do usuário 1 — recebe 404 (RGN-10)."""
    token_one = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    token_two = _login(client, regular_user_two.email, os.environ["TEST_USER_TWO_PASSWORD"])

    doc_id = _upload_contract(client, token_one)

    response = client.post(
        f"/api/v1/documents/{doc_id}/benchmark-compression",
        headers=_bearer(token_two),
        json={},
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_benchmark_documento_inexistente_retorna_404(
    client: TestClient,
    regular_user_one: User,
) -> None:
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    nil_uuid = "00000000-0000-0000-0000-000000000099"

    response = client.post(
        f"/api/v1/documents/{nil_uuid}/benchmark-compression",
        headers=_bearer(token),
        json={},
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_benchmark_target_dim_invalido_retorna_422(
    client: TestClient,
    regular_user_one: User,
) -> None:
    """target_dim=1 viola Field(ge=2) no schema."""
    token = _login(client, regular_user_one.email, os.environ["TEST_USER_ONE_PASSWORD"])
    nil_uuid = "00000000-0000-0000-0000-000000000001"

    response = client.post(
        f"/api/v1/documents/{nil_uuid}/benchmark-compression",
        headers=_bearer(token),
        json={"target_dim": _INVALID_TARGET_DIM},
    )
    assert response.status_code == 422
