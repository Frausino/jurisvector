"""Endpoints REST de autenticação e autocadastro.

Endpoints:
- POST /api/v1/auth/login     (já existia; preservado)
- GET  /api/v1/auth/me        (já existia; preservado)
- POST /api/v1/auth/register  (anti-enum completo)

Defesa anti-enumeração em `/register`:

1.  Rate limit por IP via slowapi.
2.  Latência mínima vinda de Settings (`REGISTER_MIN_LATENCY_SECONDS`,
    default 0.6s) — DEVE ser maior que um bcrypt no cost de produção.
3.  Resposta 201 com payload genérico em AMBOS os caminhos (criado
    real ou email duplicado). A distinção fica APENAS no audit log
    (forense), nunca no contrato HTTP.
4.  Hash dummy do bcrypt executado também no caminho duplicado (no
    use case), igualando o custo computacional.
"""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Request, status

from docuvector.api.deps import (
    AuthUseCaseDependency,
    ClientIpDependency,
    CurrentTokenDependency,
    RegisterUserUseCaseDependency,
)
from docuvector.api.limiting import shared_limiter
from docuvector.api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegistrationAcknowledgement,
    UserResponse,
)
from docuvector.config.settings import get_settings

_settings = get_settings()
_LOGIN_RATE = f"{_settings.login_rate_limit_per_minute}/minute"
_REGISTER_RATE = f"{_settings.register_rate_limit_per_minute}/minute"

# Jitter aleatório de até 30ms para destruir fingerprint do piso fixo.
_MAX_JITTER_MILLISECONDS = 30

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# =============================================================
# POST /login
# =============================================================
@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticar usuário",
    responses={
        401: {"description": "Credenciais inválidas."},
        429: {"description": "Limite de tentativas excedido."},
    },
)
@shared_limiter.limit(_LOGIN_RATE)
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


# =============================================================
# GET /me
# =============================================================
@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Recuperar usuário autenticado",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def me(
    token_payload: CurrentTokenDependency,
    auth_use_case: AuthUseCaseDependency,
) -> UserResponse:
    user = auth_use_case.me(token_payload)
    return UserResponse.model_validate(user)


# =============================================================
# POST /register
# =============================================================
@router.post(
    "/register",
    response_model=RegistrationAcknowledgement,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-cadastro de usuário",
    description=(
        "Cria uma nova conta com papel `user`. A senha é validada por "
        "política NIST SP 800-63B (mínimo 12 caracteres, bloqueio de "
        "senhas vazadas, sem similaridade com identificador).\n\n"
        "Para impedir enumeração de e-mails cadastrados, este endpoint "
        "retorna sempre a mesma resposta genérica (201) e a mesma "
        "latência mínima, independentemente do e-mail já existir."
    ),
    responses={
        201: {"description": "Solicitação de cadastro recebida."},
        422: {"description": "Senha não atende à política."},
        429: {"description": "Limite de tentativas excedido."},
    },
)
@shared_limiter.limit(_REGISTER_RATE)
def register(
    request: Request,
    payload: RegisterRequest,
    register_use_case: RegisterUserUseCaseDependency,
    client_ip: ClientIpDependency,
) -> RegistrationAcknowledgement:
    request_started_at = time.perf_counter()
    user_agent_header = request.headers.get("user-agent")

    try:
        register_use_case.register(
            email=payload.email,
            plain_password=payload.password,
            client_ip=client_ip,
            user_agent=user_agent_header,
        )
        return RegistrationAcknowledgement(
            message=(
                "Solicitação de cadastro recebida. Se este e-mail ainda não "
                "estiver em uso, a conta foi criada e você já pode fazer login."
            ),
        )
    finally:
        _equalize_latency(started_at=request_started_at)


def _equalize_latency(started_at: float) -> None:
    """Sleep complementar para alcançar o piso de latência mínima.

    O floor `REGISTER_MIN_LATENCY_SECONDS` precisa ser maior que o tempo
    de execução de um bcrypt no cost de produção (cost 12 ≈ 250-400ms
    dependendo do hardware). Quando o caminho real é mais rápido que
    o floor, dormimos a diferença. Jitter cripto-seguro de até 30ms
    impede que atacantes fingerprintem o piso exato.
    """
    minimum_latency_seconds = get_settings().register_min_latency_seconds
    elapsed_seconds = time.perf_counter() - started_at
    remaining_seconds = minimum_latency_seconds - elapsed_seconds

    if remaining_seconds <= 0:
        # Caminho normal: bcrypt levou mais que o floor. Não dormimos
        # negativo. Risco residual: se a variação entre runs for grande,
        # ainda há sinal. Subir REGISTER_MIN_LATENCY_SECONDS é o mitigador.
        return

    jitter_milliseconds = secrets.randbelow(_MAX_JITTER_MILLISECONDS + 1)
    time.sleep(remaining_seconds + jitter_milliseconds / 1000)
