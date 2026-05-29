from __future__ import annotations

from fastapi import APIRouter, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from docuvector.api.deps import (
    AuthUseCaseDependency,
    ClientIpDependency,
    CurrentTokenDependency,
)
from docuvector.api.schemas.auth import LoginRequest, LoginResponse, UserResponse
from docuvector.config.settings import get_settings

_settings = get_settings()
_LOGIN_RATE = f"{_settings.login_rate_limit_per_minute}/minute"

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticar usuário",
    description=(
        "Recebe e-mail e senha e devolve um token JWT.\n\n"
        "Mensagens de erro são intencionalmente genéricas para impedir "
        "enumeração de e-mails válidos. Tentativas falhas são registradas "
        "no log de auditoria."
    ),
    responses={
        401: {"description": "Credenciais inválidas."},
        429: {"description": "Limite de tentativas excedido."},
    },
)
@limiter.limit(_LOGIN_RATE)
def login(
    request: Request,
    payload: LoginRequest,
    auth_use_case: AuthUseCaseDependency,
    client_ip: ClientIpDependency,
) -> LoginResponse:
    user_agent_header = request.headers.get("user-agent")
    login_result = auth_use_case.login(
        email=payload.email,
        plain_password=payload.password,
        client_ip=client_ip,
        user_agent=user_agent_header,
    )

    return LoginResponse(
        access_token=login_result.access_token,
        token_type=login_result.token_type,
        expires_in=login_result.expires_in_seconds,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Recuperar usuário autenticado",
    description="Retorna os dados do usuário cujo JWT foi enviado no header.",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def me(
    token_payload: CurrentTokenDependency,
    auth_use_case: AuthUseCaseDependency,
) -> UserResponse:
    user = auth_use_case.me(token_payload)
    return UserResponse.model_validate(user)
