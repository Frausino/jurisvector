"""Dependency providers para injeção em routers FastAPI.

Único módulo da camada de apresentação que conhece as implementações
concretas. Tudo o que vive aqui é "wiring": montar o use case com
suas dependências infra-resolvidas a partir do Settings.
"""

from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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

# Esquema de segurança Bearer. auto_error=False para que a ausência de
# credenciais produza nosso 401 padronizado (com WWW-Authenticate), em vez
# do 403 genérico do FastAPI. Registrar este esquema faz o Swagger exibir
# o botão "Authorize" (cadeado), que injeta o prefixo Bearer automaticamente.
_bearer_scheme = HTTPBearer(auto_error=False)


# =============================================================
# Configuração
# =============================================================
def provide_settings() -> Settings:
    """Injeta o objeto Settings cacheado."""
    return get_settings()


SettingsDependency = Annotated[Settings, Depends(provide_settings)]
SessionDependency = Annotated[Session, Depends(provide_session)]


# =============================================================
# Serviços de segurança (singletons de processo)
# =============================================================
@lru_cache(maxsize=1)
def get_password_hasher() -> BcryptPasswordHasher:
    """Hasher bcrypt singleton de processo.

    Cacheado porque o CryptContext do passlib é caro de construir e é
    thread-safe para hash/verify. Reconstruí-lo por request desperdiçava
    CPU e anulava o cache do timing equalizer no AuthUseCase.
    O cost é resolvido por ambiente (ver Settings.effective_bcrypt_rounds).
    """
    return BcryptPasswordHasher(rounds=get_settings().effective_bcrypt_rounds)


@lru_cache(maxsize=1)
def get_token_service() -> JwtTokenService:
    """Serviço JWT singleton de processo, configurado a partir do Settings."""
    settings = get_settings()
    return JwtTokenService(
        secret_key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


def provide_token_service() -> JwtTokenService:
    """Dependency FastAPI que devolve o serviço JWT singleton."""
    return get_token_service()


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

    O `password_hasher` é o singleton de processo (get_password_hasher),
    não uma instância nova por request. Isso preserva o cache do timing
    equalizer entre requisições.
    """
    return AuthUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        password_hasher=get_password_hasher(),
        token_service=token_service,
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
        token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


AuthUseCaseDependency = Annotated[AuthUseCase, Depends(provide_auth_use_case)]


# =============================================================
# Autenticação via esquema Bearer (HTTPBearer)
# =============================================================
def require_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    token_service: TokenServiceDependency,
) -> TokenPayload:
    """Dependency que protege rotas exigindo JWT válido no esquema Bearer.

    Usa `HTTPBearer`, que extrai o token do header `Authorization: Bearer <token>`
    e registra o esquema no OpenAPI (botão Authorize no Swagger).
    Retorna o `TokenPayload`; o router pode então chamar `auth_use_case.me()`.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return token_service.verify(credentials.credentials)
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


def _normalize_ip(candidate: str | None) -> str | None:
    """Valida e normaliza um IP textual.

    Retorna o IP canônico em string ou `None` quando o valor é vazio,
    malformado ou não representa um endereço IP real.
    """
    if not candidate:
        return None

    normalized_candidate = candidate.strip()
    if not normalized_candidate:
        return None

    try:
        return str(ip_address(normalized_candidate))
    except ValueError:
        return None


def get_client_ip(
    forwarded_for: Annotated[str | None, Header(alias="X-Forwarded-For")] = None,
    real_ip: Annotated[str | None, Header(alias="X-Real-IP")] = None,
) -> str | None:
    def _normalize(value: str | None) -> str | None:
        if not value:
            return None
        candidate = value.strip()
        try:
            return str(ip_address(candidate))
        except ValueError:
            return None

    if forwarded_for:
        first_ip = forwarded_for.split(",", maxsplit=1)[0]
        normalized = _normalize(first_ip)
        if normalized:
            return normalized

    normalized = _normalize(real_ip)
    if normalized:
        return normalized

    return None


ClientIpDependency = Annotated[str | None, Depends(get_client_ip)]
