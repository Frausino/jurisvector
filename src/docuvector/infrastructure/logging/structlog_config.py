"""Configuração centralizada de logging estruturado via structlog.

Em desenvolvimento renderiza no console com cores. Em produção e em
ambientes onde o nível for diferente, emite JSON serializável para
agregadores de log.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import structlog

from docuvector.config.settings import ApplicationEnvironment, Settings


def configure_logging(settings: Settings) -> None:
    """Configura o logger estruturado para o processo atual.

    Deve ser chamado exatamente uma vez, no startup da aplicação.
    """
    numeric_level = logging.getLevelName(settings.log_level)
    logging.basicConfig(format="%(message)s", level=numeric_level)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    final_renderer: Any
    if settings.app_env is ApplicationEnvironment.DEVELOPMENT:
        final_renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        final_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, final_renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Atalho semântico para obter um logger contextualizado."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
