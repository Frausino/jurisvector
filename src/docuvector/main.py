"""Entrypoint da aplicação FastAPI.

Usa o padrão factory (`create_app`) para permitir múltiplas instâncias
em testes e injeção controlada de dependências. A instância exportada
no nível do módulo (`app`) é a usada por `uvicorn docuvector.main:app`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from docuvector import __version__
from docuvector.api.routers import health
from docuvector.config.settings import Settings, get_settings
from docuvector.infrastructure.logging.structlog_config import (
    configure_logging,
    get_logger,
)


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hook de inicialização e finalização da aplicação.

    Inicializa logging estruturado no startup. Na Sprint 2 também
    fará warmup do engine SQLAlchemy e do cliente Chroma.
    """
    settings: Settings = get_settings()
    configure_logging(settings)
    logger = get_logger("docuvector.startup")
    logger.info(
        "application_started",
        version=__version__,
        environment=settings.app_env.value,
        port=settings.app_port,
    )

    yield

    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Constrói a instância FastAPI da aplicação."""
    settings = get_settings()

    fastapi_app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Sistema RAG com compressão observável de embeddings, "
            "benchmark de provedores e isolamento multi-tenant."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=application_lifespan,
    )

    # CORS apenas para o próprio front local em desenvolvimento.
    # Em produção real seria controlado por proxy reverso.
    if settings.is_development:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=[f"http://{settings.app_host}:{settings.app_port}"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    fastapi_app.include_router(health.router)

    return fastapi_app


app = create_app()
