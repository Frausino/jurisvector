"""Entrypoint da aplicação FastAPI.

Usa o padrão factory (`create_app`) para permitir múltiplas instâncias
em testes e injeção controlada de dependências.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from docuvector import __version__
from docuvector.api.limiting import shared_limiter
from docuvector.api.routers import admin_users as admin_users_router
from docuvector.api.routers import auth as auth_router
from docuvector.api.routers import documents as documents_router
from docuvector.api.routers import health
from docuvector.api.routers import metrics as metrics_router
from docuvector.api.routers import queries as queries_router
from docuvector.api.web import router as web_router
from docuvector.config.settings import Settings, get_settings
from docuvector.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateResourceError,
    LlmGenerationError,
    ResourceNotFoundError,
    ValidationError,
)
from docuvector.infrastructure.logging.structlog_config import (
    configure_logging,
    get_logger,
)


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hook de inicialização e finalização da aplicação."""
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

    fastapi_app.state.limiter = shared_limiter
    fastapi_app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_handler,  # type: ignore[arg-type]
    )

    fastapi_app.add_exception_handler(
        AuthenticationError,
        _authentication_error_handler,  # type: ignore[arg-type]
    )
    fastapi_app.add_exception_handler(
        AuthorizationError,
        _authorization_error_handler,  # type: ignore[arg-type]
    )
    fastapi_app.add_exception_handler(
        ResourceNotFoundError,
        _not_found_handler,  # type: ignore[arg-type]
    )
    fastapi_app.add_exception_handler(
        ValidationError,
        _validation_error_handler,  # type: ignore[arg-type]
    )
    fastapi_app.add_exception_handler(
        DuplicateResourceError,
        _duplicate_resource_handler,  # type: ignore[arg-type]
    )
    fastapi_app.add_exception_handler(
        LlmGenerationError,
        _llm_generation_handler,  # type: ignore[arg-type]
    )

    if settings.is_development:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=[f"http://{settings.app_host}:{settings.app_port}"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    fastapi_app.include_router(health.router)
    fastapi_app.include_router(auth_router.router)
    fastapi_app.include_router(documents_router.router)
    fastapi_app.include_router(admin_users_router.router)
    fastapi_app.include_router(queries_router.router)
    fastapi_app.include_router(metrics_router.router)

    # Camada web (server-side rendering). Registrada por último para
    # que as rotas de API tenham precedência na resolução.
    _static_dir = Path(__file__).resolve().parent / "api" / "static"
    fastapi_app.mount(
        "/static",
        StaticFiles(directory=str(_static_dir)),
        name="static",
    )
    fastapi_app.include_router(web_router)

    return fastapi_app


# =============================================================
# Handlers de exceção (mapeamento domínio -> HTTP)
# =============================================================
def _build_error_response(http_status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message}},
    )


async def _authentication_error_handler(
    _request: Request, exc: AuthenticationError
) -> JSONResponse:
    response = _build_error_response(
        status.HTTP_401_UNAUTHORIZED, "authentication_failed", str(exc)
    )
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


async def _authorization_error_handler(_request: Request, exc: AuthorizationError) -> JSONResponse:
    return _build_error_response(status.HTTP_403_FORBIDDEN, "forbidden", str(exc))


async def _not_found_handler(_request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    return _build_error_response(status.HTTP_404_NOT_FOUND, "not_found", str(exc))


async def _validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    return _build_error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error", str(exc))


async def _duplicate_resource_handler(
    _request: Request, exc: DuplicateResourceError
) -> JSONResponse:
    return _build_error_response(status.HTTP_409_CONFLICT, "duplicate_resource", str(exc))


async def _llm_generation_handler(_request: Request, exc: LlmGenerationError) -> JSONResponse:
    """LLM upstream falhou: traduz como 502 Bad Gateway.

    Mensagem genérica para o cliente (não vazamos detalhes internos da
    OpenAI), mas o audit log já registrou a falha completa com
    correlação ao usuário.
    """
    return _build_error_response(
        status.HTTP_502_BAD_GATEWAY,
        "llm_upstream_failure",
        "Não foi possível gerar uma resposta neste momento. Tente novamente.",
    )


async def _rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return _build_error_response(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limit_exceeded",
        f"Limite excedido: {exc.detail}",
    )


app = create_app()
