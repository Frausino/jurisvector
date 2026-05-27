"""Dependency providers para injeção em routers FastAPI.

Único módulo da camada de apresentação que conhece as implementações
concretas. Tudo o que vive aqui é "wiring": montar o use case com
suas dependências infra-resolvidas a partir do Settings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from docuvector.application.auth_use_case import AuthUseCase
from docuvector.config.settings import Settings, get_settings
from docuvector.domain.enums import UserRole
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces.token_service import TokenPayload
from docuvector.infrastructure.persistence.audit_repository_impl import SqlAlchemyAuditRepository
from docuvector.infrastructure.persistence.database import get_session_factory, provide_session
from docuvector.infrastructure.persistence.user_repository_impl import SqlAlchemyUserRepository
from docuvector.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher
from docuvector.infrastructure.security.jwt_service import JwtTokenService


# =============================================================
# Configuração
# =============================================================
def provide_settings() -> Settings:
    """Injeta o objeto Settings cacheado."""
    return get_settings()


SettingsDependency = Annotated[Settings, Depends(provide_settings)]
SessionDependency = Annotated[Session, Depends(provide_session)]


# =============================================================
# Serviços de segurança (singletons por requisição; baratos de criar)
# =============================================================
def provide_password_hasher() -> BcryptPasswordHasher:
    """Hasher bcrypt com cost padrão 12."""
    return BcryptPasswordHasher()


def provide_token_service(settings: SettingsDependency) -> JwtTokenService:
    """Serviço JWT configurado a partir do Settings."""
    return JwtTokenService(
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


TokenServiceDependency = Annotated[JwtTokenService, Depends(provide_token_service)]


# =============================================================
# Use cases
# =============================================================
def provide_auth_use_case(
    session: SessionDependency,
    settings: SettingsDependency,
    token_service: TokenServiceDependency,
) -> AuthUseCase:
    """Monta o `AuthUseCase` com todas as dependências concretas.

    Atenção: `AuditRepository` recebe o `session_factory` (não a session
    do request), porque audit log é transação autônoma. Ver
    `audit_repository_impl.py` para a justificativa NIST SP 800-53 AU-2.
    """
    return AuthUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        password_hasher=provide_password_hasher(),
        token_service=token_service,
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
        token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


AuthUseCaseDependency = Annotated[AuthUseCase, Depends(provide_auth_use_case)]


# =============================================================
# Autenticação por header Authorization: Bearer <token>
# =============================================================
def require_authenticated_user(
    token_service: TokenServiceDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenPayload:
    """Dependency que protege rotas exigindo JWT válido.

    Retorna o `TokenPayload`. O router pode então chamar
    `auth_use_case.me(payload)` para obter a entidade fresh do banco.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = authorization.split(" ", 1)[1].strip()
    try:
        return token_service.verify(raw_token)
    except AuthenticationError as authentication_failure:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from authentication_failure


CurrentTokenDependency = Annotated[TokenPayload, Depends(require_authenticated_user)]


def require_admin(token_payload: CurrentTokenDependency) -> TokenPayload:
    """Reforça que o usuário autenticado tem papel `admin`.

    Usado em rotas administrativas (auditoria, métricas globais).
    """

    if token_payload.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return token_payload


def get_client_ip(
    forwarded_for: Annotated[str | None, Header(alias="X-Forwarded-For")] = None,
    real_ip: Annotated[str | None, Header(alias="X-Real-IP")] = None,
) -> str | None:
    """Extrai o IP do cliente, considerando proxies reversos comuns.

    Em desenvolvimento (localhost direto) retorna None; o router
    persiste como NULL no audit_logs. Em produção com proxy, lê
    o primeiro IP de X-Forwarded-For.
    """
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if real_ip:
        return real_ip.strip()
    return None


ClientIpDependency = Annotated[str | None, Depends(get_client_ip)]
