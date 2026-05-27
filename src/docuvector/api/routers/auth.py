"""Router de autenticação: `/api/v1/auth/login` e `/api/v1/auth/me`.

Traduz HTTP <-> use case. Sem regra de negócio aqui.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from docuvector.api.deps import (
    AuthUseCaseDependency,
    ClientIpDependency,
    CurrentTokenDependency,
)
from docuvector.api.schemas.auth import LoginRequest, LoginResponse, UserResponse
from docuvector.config.settings import get_settings
from docuvector.domain.exceptions import AuthenticationError

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
    request: Request,  # exigido pelo slowapi; mantido para anti-flake8
    payload: LoginRequest,
    auth_use_case: AuthUseCaseDependency,
    client_ip: ClientIpDependency,
) -> LoginResponse:
    user_agent_header = request.headers.get("user-agent")
    try:
        login_result = auth_use_case.login(
            email=payload.email,
            plain_password=payload.password,
            client_ip=client_ip or request.client.host if request.client else client_ip,
            user_agent=user_agent_header,
        )
    except AuthenticationError as authentication_failure:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(authentication_failure),
            headers={"WWW-Authenticate": "Bearer"},
        ) from authentication_failure

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
    try:
        user = auth_use_case.me(token_payload)
    except AuthenticationError as session_failure:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(session_failure),
            headers={"WWW-Authenticate": "Bearer"},
        ) from session_failure

    return UserResponse.model_validate(user)
