"""Smoke test do endpoint de saúde."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docuvector import __version__


@pytest.mark.integration
def test_health_endpoint_returns_ok_payload(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["application"] == "DocuVector Lite"
    assert payload["version"] == __version__
    assert payload["environment"] in {"development", "test", "production"}


@pytest.mark.integration
def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "DocuVector Lite"
    assert "/api/v1/health" in schema["paths"]


@pytest.mark.integration
def test_swagger_ui_is_served(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()
