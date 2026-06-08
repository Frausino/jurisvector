"""Configuração compartilhada da camada web: templates e contexto.

Centraliza a instância de Jinja2Templates para que todos os routers
de view usem o mesmo diretório e os mesmos globals.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from docuvector.api.deps import SESSION_COOKIE_NAME
from docuvector.config.settings import get_settings
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces.token_service import TokenPayload
from docuvector.infrastructure.security.jwt_service import JwtTokenService

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def current_user_or_none(request: Request) -> TokenPayload | None:
    """Lê o usuário do cookie de sessão sem levantar exceção.

    Usado por páginas que se comportam de forma diferente para
    visitantes e usuários logados (ex.: a navbar). Não substitui a
    proteção de rota, que continua via CurrentTokenDependency.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    settings = get_settings()

    token_service = JwtTokenService(
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )
    try:
        return token_service.verify(token)
    except AuthenticationError:
        return None
