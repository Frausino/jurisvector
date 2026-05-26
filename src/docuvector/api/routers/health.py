"""Router de saúde da aplicação (`/api/v1/health`).

Endpoint público (sem autenticação) usado para verificações de readiness
e liveness. Na Sprint 1, retorna apenas estado do processo. A partir da
Sprint 2, passa a validar conectividade com o PostgreSQL.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from docuvector import __version__
from docuvector.config.settings import ApplicationEnvironment, get_settings


class HealthResponse(BaseModel):
    """Resposta do endpoint de saúde."""

    status: Literal["ok"] = Field(description="Estado do processo da aplicação.")
    application: str = Field(description="Nome do produto.")
    version: str = Field(description="Versão semântica em execução.")
    environment: ApplicationEnvironment = Field(description="Ambiente ativo.")


router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificação de saúde",
    description=(
        "Retorna o estado atual do processo. Endpoint público, sem autenticação. "
        "Usado por orquestradores e pela demonstração para validar que a aplicação "
        "subiu corretamente."
    ),
)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        application=settings.app_name,
        version=__version__,
        environment=settings.app_env,
    )
