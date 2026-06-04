"""Dependency providers para injeção em routers FastAPI."""

from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from docuvector.application.admin_user_management_use_case import (
    AdminUserManagementUseCase,
)
from docuvector.application.answer_use_case import AnswerUseCase
from docuvector.application.auth_use_case import AuthUseCase
from docuvector.application.compression_benchmark_use_case import (
    CompressionBenchmarkUseCase,
)
from docuvector.application.document_crud_use_case import DocumentCrudUseCase
from docuvector.application.ingestion_use_case import IngestionUseCase
from docuvector.application.register_user_use_case import RegisterUserUseCase
from docuvector.application.retrieval_use_case import RetrievalUseCase
from docuvector.config.settings import Settings, get_settings
from docuvector.domain.enums import UserRole
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces.password_policy_validator import (
    PasswordPolicyValidator,
)
from docuvector.domain.interfaces.token_service import TokenPayload
from docuvector.infrastructure.chunking.recursive_splitter import (
    RecursiveSplitter,
)
from docuvector.infrastructure.persistence.audit_repository_impl import (
    SqlAlchemyAuditRepository,
)
from docuvector.infrastructure.persistence.database import (
    get_session_factory,
    provide_session,
)
from docuvector.infrastructure.persistence.document_repository_impl import (
    SqlAlchemyDocumentRepository,
)
from docuvector.infrastructure.persistence.user_repository_impl import (
    SqlAlchemyUserRepository,
)
from docuvector.infrastructure.security.bcrypt_hasher import (
    BcryptPasswordHasher,
)
from docuvector.infrastructure.security.jwt_service import JwtTokenService
from docuvector.infrastructure.security.nist_password_policy_validator import (
    NistPasswordPolicyValidator,
)
from docuvector.infrastructure.vector_stores.chroma_vector_store import (
    ChromaVectorStore,
)

_bearer_scheme = HTTPBearer(auto_error=False)


# =============================================================
# Configuração
# =============================================================


SettingsDependency = Annotated[
    Settings,
    Depends(get_settings),
]
SessionDependency = Annotated[Session, Depends(provide_session)]


# =============================================================
# Serviços de segurança (singletons de processo)
# =============================================================
@lru_cache(maxsize=1)
def get_password_hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher(rounds=get_settings().effective_bcrypt_rounds)


@lru_cache(maxsize=1)
def get_token_service() -> JwtTokenService:
    settings = get_settings()
    return JwtTokenService(
        secret_key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


TokenServiceDependency = Annotated[
    JwtTokenService,
    Depends(get_token_service),
]


@lru_cache(maxsize=1)
def get_password_policy() -> PasswordPolicyValidator:
    """Singleton stateless. `validate` recebe owner_identifier por chamada."""
    settings = get_settings()
    return NistPasswordPolicyValidator(min_length=settings.password_min_length)


PasswordPolicyDependency = Annotated[
    PasswordPolicyValidator,
    Depends(get_password_policy),
]


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore:
    settings = get_settings()
    return ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name="docuvector",
    )


VectorStoreDependency = Annotated[
    ChromaVectorStore,
    Depends(get_vector_store),
]


# =============================================================
# Use cases
# =============================================================
def provide_auth_use_case(
    session: SessionDependency,
    settings: SettingsDependency,
    token_service: TokenServiceDependency,
) -> AuthUseCase:
    return AuthUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        password_hasher=get_password_hasher(),
        token_service=token_service,
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
        token_expire_minutes=settings.jwt_access_token_expire_minutes,
    )


AuthUseCaseDependency = Annotated[AuthUseCase, Depends(provide_auth_use_case)]


def provide_register_user_use_case(
    session: SessionDependency,
) -> RegisterUserUseCase:
    return RegisterUserUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        password_hasher=get_password_hasher(),
        password_policy=get_password_policy(),
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
    )


RegisterUserUseCaseDependency = Annotated[
    RegisterUserUseCase,
    Depends(provide_register_user_use_case),
]


def provide_admin_user_management_use_case(
    session: SessionDependency,
) -> AdminUserManagementUseCase:
    return AdminUserManagementUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        password_hasher=get_password_hasher(),
        password_policy=get_password_policy(),
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
    )


AdminUserManagementUseCaseDependency = Annotated[
    AdminUserManagementUseCase,
    Depends(provide_admin_user_management_use_case),
]


def provide_document_crud_use_case(
    session: SessionDependency,
) -> DocumentCrudUseCase:
    return DocumentCrudUseCase(
        document_repository=SqlAlchemyDocumentRepository(session),
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
    )


DocumentCrudUseCaseDependency = Annotated[
    DocumentCrudUseCase,
    Depends(provide_document_crud_use_case),
]


def provide_ingestion_use_case(
    session: SessionDependency,
    settings: SettingsDependency,
    vector_store: VectorStoreDependency,
) -> IngestionUseCase:
    splitter = RecursiveSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )

    return IngestionUseCase(
        document_repository=SqlAlchemyDocumentRepository(session),
        text_splitter=splitter,
        vector_store=vector_store,
        audit_repository=SqlAlchemyAuditRepository(
            get_session_factory(),
        ),
        upload_max_bytes=settings.upload_max_bytes,
    )


IngestionUseCaseDependency = Annotated[
    IngestionUseCase,
    Depends(provide_ingestion_use_case),
]


def provide_answer_use_case(
    vector_store: VectorStoreDependency,
) -> AnswerUseCase:
    """Constrói o AnswerUseCase sem amarrar a um LLM específico.

    O `LlmClient` concreto é resolvido pelo router a cada request a
    partir do campo `llm_provider`, e passado explicitamente para
    `ask()`. Aqui só montamos o retrieval e o audit, que são
    invariantes do fluxo.
    """
    settings = get_settings()

    retrieval_use_case = RetrievalUseCase(
        vector_store=vector_store,
        default_top_k=settings.rag_top_k,
        default_similarity_threshold=settings.rag_similarity_threshold,
    )

    return AnswerUseCase(
        retrieval_use_case=retrieval_use_case,
        audit_repository=SqlAlchemyAuditRepository(
            get_session_factory(),
        ),
    )


AnswerUseCaseDependency = Annotated[
    AnswerUseCase,
    Depends(provide_answer_use_case),
]


def provide_compression_benchmark_use_case(
    session: SessionDependency,
    vector_store: VectorStoreDependency,
) -> CompressionBenchmarkUseCase:
    """Constrói o use case de benchmark reutilizando o VectorStore singleton.

    Usa `VectorStoreDependency` (já existe no deps.py) para não criar
    uma segunda instância do Chroma por request — o ChromaVectorStore
    é caro de construir (abre conexão com o banco de vetores).
    """
    return CompressionBenchmarkUseCase(
        document_repository=SqlAlchemyDocumentRepository(session),
        vector_store=vector_store,
        audit_repository=SqlAlchemyAuditRepository(
            get_session_factory(),
        ),
    )


CompressionBenchmarkUseCaseDependency = Annotated[
    CompressionBenchmarkUseCase,
    Depends(provide_compression_benchmark_use_case),
]


# =============================================================
# Autenticação via esquema Bearer (HTTPBearer)
# =============================================================
def require_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    token_service: TokenServiceDependency,
) -> TokenPayload:
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
    if token_payload.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return token_payload


AdminTokenDependency = Annotated[TokenPayload, Depends(require_admin)]


# =============================================================
# Resolução de IP do cliente com validação anti-spoofing
# =============================================================
def _normalize_ip(candidate: str | None) -> str | None:
    """Valida sintaticamente um IP textual."""
    if not candidate:
        return None
    normalized = candidate.strip()
    if not normalized:
        return None
    try:
        return str(ip_address(normalized))
    except ValueError:
        return None


def _extract_peer_ip(request: Request) -> str | None:
    """Devolve o IP do peer TCP direto, validado sintaticamente."""
    if request.client is None:
        return None
    return _normalize_ip(request.client.host)


def get_client_ip(
    request: Request,
    settings: SettingsDependency,
    forwarded_for: Annotated[str | None, Header(alias="X-Forwarded-For")] = None,
    real_ip: Annotated[str | None, Header(alias="X-Real-IP")] = None,
) -> str | None:
    """Resolve o IP do cliente com defesa anti-spoofing.

    Política:
    1.  Se o peer TCP direto está em `trusted_proxy_ips`, lemos os
        headers `X-Forwarded-For` / `X-Real-IP` confiando neles.
    2.  Caso contrário, ignoramos esses headers (poderiam ser forjados
        pelo próprio cliente) e usamos o peer TCP direto.
    3.  Se a allowlist estiver vazia (default em dev), também
        confiamos nos headers, com aviso de que isso é apenas
        adequado a localhost.
    """
    peer_ip = _extract_peer_ip(request)
    trusted_proxies = settings.trusted_proxy_ip_set

    headers_can_be_trusted = (not trusted_proxies) or (peer_ip in trusted_proxies)

    if headers_can_be_trusted:
        if forwarded_for:
            first_ip_in_chain = forwarded_for.split(",", maxsplit=1)[0]
            normalized = _normalize_ip(first_ip_in_chain)
            if normalized:
                return normalized
        normalized_real_ip = _normalize_ip(real_ip)
        if normalized_real_ip:
            return normalized_real_ip

    return peer_ip


ClientIpDependency = Annotated[str | None, Depends(get_client_ip)]
