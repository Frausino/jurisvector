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
from docuvector.application.compare_retrieval_use_case import CompareRetrievalUseCase
from docuvector.application.compress_to_collection_use_case import (
    CompressToCollectionUseCase,
)
from docuvector.application.compression_benchmark_use_case import (
    CompressionBenchmarkUseCase,
)
from docuvector.application.document_crud_use_case import DocumentCrudUseCase
from docuvector.application.embedding_benchmark_use_case import (
    EmbeddingBenchmarkUseCase,
)
from docuvector.application.ingestion_use_case import IngestionUseCase
from docuvector.application.metrics_use_case import MetricsUseCase
from docuvector.application.multi_collection_ingestion_use_case import (
    MultiCollectionIngestionUseCase,
)
from docuvector.application.register_user_use_case import RegisterUserUseCase
from docuvector.application.retrieval_use_case import RetrievalUseCase
from docuvector.config.settings import Settings, get_settings
from docuvector.domain.enums import (
    CompressionMethod,
    EmbeddingProviderName,
    UserRole,
)
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces import VectorStore
from docuvector.domain.interfaces.password_policy_validator import (
    PasswordPolicyValidator,
)
from docuvector.domain.interfaces.token_service import TokenPayload
from docuvector.infrastructure.chunking.recursive_splitter import (
    RecursiveSplitter,
)
from docuvector.infrastructure.compression.binary_compressor import BinaryCompressor
from docuvector.infrastructure.compression.int8_compressor import Int8Compressor
from docuvector.infrastructure.compression.random_projection_compressor import (
    RandomProjectionCompressor,
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
from docuvector.infrastructure.vector_stores.compressed_vector_store import (
    CompressedVectorStore,
)
from docuvector.infrastructure.vector_stores.corpus_pca_store import CorpusPcaStore

# Alias de tipo para o par (método de compressão, vector store).
# Usa VectorStore (Protocol) em vez de tipos concretos para desacoplamento.
# CompressedVectorStore e CorpusPcaStore implementam VectorStore
# implicitamente (structural subtyping via Protocol).
StoreEntry = tuple[CompressionMethod, VectorStore]

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
        collection_name=settings.chroma_collection_original,
    )


VectorStoreDependency = Annotated[
    ChromaVectorStore,
    Depends(get_vector_store),
]


@lru_cache(maxsize=1)
def _get_int8_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_int8,
    )
    return CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())


@lru_cache(maxsize=1)
def _get_binary_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_binary,
    )
    return CompressedVectorStore(inner_store=inner, compressor=BinaryCompressor())


@lru_cache(maxsize=1)
def _get_pca_store() -> VectorStore:
    """PCA treinado no corpus completo — espaço vetorial consistente.
    Ver CorpusPcaStore para documentação do GAP 2."""
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_pca,
    )
    return CorpusPcaStore(
        inner_store=inner,
        target_dim=settings.chroma_pca_target_dim,
    )


@lru_cache(maxsize=1)
def _get_rp_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_rp,
    )
    return CompressedVectorStore(
        inner_store=inner,
        compressor=RandomProjectionCompressor(target_dim=settings.chroma_pca_target_dim),
    )


def _all_compressed_stores() -> list[StoreEntry]:
    """Retorna todas as coleções comprimidas com seus métodos correspondentes."""
    return [
        (CompressionMethod.INT8, _get_int8_store()),
        (CompressionMethod.BINARY, _get_binary_store()),
        (CompressionMethod.PCA, _get_pca_store()),
        (CompressionMethod.RANDOM_PROJECTION, _get_rp_store()),
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
    vector_store: VectorStoreDependency,
) -> MultiCollectionIngestionUseCase:
    """Use case de ingestão que grava na coleção original e nas 4 comprimidas."""

    settings = get_settings()
    primary = IngestionUseCase(
        document_repository=SqlAlchemyDocumentRepository(session),
        text_splitter=RecursiveSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        ),
        vector_store=vector_store,
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
        upload_max_bytes=settings.upload_max_bytes,
    )
    return MultiCollectionIngestionUseCase(
        primary_ingestion=primary,
        primary_vector_store=vector_store,
        compressed_stores=_all_compressed_stores(),
        document_repository=SqlAlchemyDocumentRepository(session),
    )


IngestionUseCaseDependency = Annotated[
    MultiCollectionIngestionUseCase,
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


def build_answer_use_case_for_store(store: VectorStore) -> AnswerUseCase:
    """Constrói AnswerUseCase com o VectorStore escolhido por request.

    Permite ao router selecionar a coleção (original, int8, binary, pca, rp)
    e o provider (ST ou OpenAI) sem alterar os singletons globais.
    """
    settings = get_settings()
    retrieval = RetrievalUseCase(
        vector_store=store,
        default_top_k=settings.rag_top_k,
        default_similarity_threshold=settings.rag_similarity_threshold,
    )
    return AnswerUseCase(
        retrieval_use_case=retrieval,
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
    )


def provide_compression_benchmark_use_case(
    session: SessionDependency,
    vector_store: VectorStoreDependency,
) -> CompressionBenchmarkUseCase:
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


def provide_embedding_benchmark_use_case(
    settings: SettingsDependency,
) -> EmbeddingBenchmarkUseCase:
    return EmbeddingBenchmarkUseCase(
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
        settings=settings,
    )


EmbeddingBenchmarkUseCaseDependency = Annotated[
    EmbeddingBenchmarkUseCase,
    Depends(provide_embedding_benchmark_use_case),
]


def provide_metrics_use_case() -> MetricsUseCase:
    """Métricas usam session factory diretamente (queries de leitura)."""
    return MetricsUseCase(session_factory=get_session_factory())


MetricsUseCaseDependency = Annotated[
    MetricsUseCase,
    Depends(provide_metrics_use_case),
]


def provide_compare_retrieval_use_case(
    vector_store: VectorStoreDependency,
) -> CompareRetrievalUseCase:
    """Use case que compara retrieval entre a coleção original e as comprimidas."""
    return CompareRetrievalUseCase(
        original_store=vector_store,
        compressed_stores=_all_compressed_stores(),
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
    )


CompareRetrievalUseCaseDependency = Annotated[
    CompareRetrievalUseCase,
    Depends(provide_compare_retrieval_use_case),
]


# =============================================================
# Stores OpenAI — coleções separadas (1536 dims)
# Nunca misturar com stores ST (384 dims): dimensões incompatíveis.
# =============================================================
@lru_cache(maxsize=1)
def _get_oai_original_store() -> ChromaVectorStore:
    settings = get_settings()
    return ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_openai_original,
    )


@lru_cache(maxsize=1)
def _get_oai_int8_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_openai_int8,
    )
    return CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())


@lru_cache(maxsize=1)
def _get_oai_binary_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_openai_binary,
    )
    return CompressedVectorStore(inner_store=inner, compressor=BinaryCompressor())


@lru_cache(maxsize=1)
def _get_oai_pca_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_openai_pca,
    )
    return CorpusPcaStore(
        inner_store=inner,
        target_dim=settings.chroma_pca_target_dim,
    )


@lru_cache(maxsize=1)
def _get_oai_rp_store() -> VectorStore:
    settings = get_settings()
    inner = ChromaVectorStore(
        persist_directory=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_openai_rp,
    )
    return CompressedVectorStore(
        inner_store=inner,
        compressor=RandomProjectionCompressor(target_dim=settings.chroma_pca_target_dim),
    )


def get_vector_store_for_provider(provider_name: str) -> ChromaVectorStore:
    """Retorna o store original correto para o provider de embedding.

    Garante que vetores ST (384 dims) e OpenAI (1536 dims) nunca
    compartilhem a mesma coleção ChromaDB.
    """
    if provider_name == EmbeddingProviderName.OPENAI.value:
        return _get_oai_original_store()
    return get_vector_store()


def resolve_vector_store_by_collection(
    collection: str,
    embedding_provider: str = EmbeddingProviderName.SENTENCE_TRANSFORMERS.value,
) -> VectorStore:
    """Resolve o VectorStore pelo nome da coleção E pelo provider de embedding.

    O provider determina qual conjunto de coleções usar:
    - sentence_transformers: docuvector, docuvector_int8, ...
    - openai: docuvector_oai, docuvector_oai_int8, ...

    Isso evita o erro 'Embedding dimension 384 does not match 1536'.
    """
    settings = get_settings()
    is_openai = embedding_provider == EmbeddingProviderName.OPENAI.value

    collection_map: dict[str, VectorStore] = (
        {
            settings.chroma_collection_openai_original: _get_oai_original_store(),
            settings.chroma_collection_openai_int8: _get_oai_int8_store(),
            settings.chroma_collection_openai_binary: _get_oai_binary_store(),
            settings.chroma_collection_openai_pca: _get_oai_pca_store(),
            settings.chroma_collection_openai_rp: _get_oai_rp_store(),
            # aliases curtos para uso no seletor do chat
            "original": _get_oai_original_store(),
            "int8": _get_oai_int8_store(),
            "binary": _get_oai_binary_store(),
            "pca": _get_oai_pca_store(),
            "random_projection": _get_oai_rp_store(),
        }
        if is_openai
        else {
            settings.chroma_collection_original: get_vector_store(),
            settings.chroma_collection_int8: _get_int8_store(),
            settings.chroma_collection_binary: _get_binary_store(),
            settings.chroma_collection_pca: _get_pca_store(),
            settings.chroma_collection_rp: _get_rp_store(),
            "original": get_vector_store(),
            "int8": _get_int8_store(),
            "binary": _get_binary_store(),
            "pca": _get_pca_store(),
            "random_projection": _get_rp_store(),
        }
    )
    return collection_map.get(collection, get_vector_store_for_provider(embedding_provider))


def provide_compress_to_collection_use_case(
    method_name: str,
    embedding_provider: str = EmbeddingProviderName.SENTENCE_TRANSFORMERS.value,
) -> CompressToCollectionUseCase:
    """Factory de CompressToCollectionUseCase para o método e provider escolhidos.

    O provider determina qual conjunto de coleções usar.
    ST (384 dims) e OpenAI (1536 dims) têm stores completamente separados.
    """
    settings = get_settings()
    is_openai = embedding_provider == EmbeddingProviderName.OPENAI.value

    st_map: dict[str, tuple[VectorStore, str]] = {
        CompressionMethod.INT8.value: (_get_int8_store(), settings.chroma_collection_int8),
        CompressionMethod.BINARY.value: (_get_binary_store(), settings.chroma_collection_binary),
        CompressionMethod.PCA.value: (_get_pca_store(), settings.chroma_collection_pca),
        CompressionMethod.RANDOM_PROJECTION.value: (_get_rp_store(), settings.chroma_collection_rp),
    }
    oai_map: dict[str, tuple[VectorStore, str]] = {
        CompressionMethod.INT8.value: (
            _get_oai_int8_store(),
            settings.chroma_collection_openai_int8,
        ),
        CompressionMethod.BINARY.value: (
            _get_oai_binary_store(),
            settings.chroma_collection_openai_binary,
        ),
        CompressionMethod.PCA.value: (_get_oai_pca_store(), settings.chroma_collection_openai_pca),
        CompressionMethod.RANDOM_PROJECTION.value: (
            _get_oai_rp_store(),
            settings.chroma_collection_openai_rp,
        ),
    }
    store_map = oai_map if is_openai else st_map
    original = _get_oai_original_store() if is_openai else get_vector_store()
    default_col = (
        settings.chroma_collection_openai_int8 if is_openai else settings.chroma_collection_int8
    )
    compressed_store, collection_name = store_map.get(
        method_name,
        (_get_oai_int8_store() if is_openai else _get_int8_store(), default_col),
    )
    return CompressToCollectionUseCase(
        original_store=original,
        compressed_store=compressed_store,
        target_collection_name=collection_name,
        document_repository=SqlAlchemyDocumentRepository(get_session_factory()()),
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
    )


def provide_ingestion_use_case_for_provider(
    session: SessionDependency,
    embedding_provider_name: str = EmbeddingProviderName.SENTENCE_TRANSFORMERS.value,
) -> MultiCollectionIngestionUseCase:
    """Cria o MultiCollectionIngestionUseCase para o provider de embedding correto.

    Garante que ST (384 dims) usa coleções docuvector_* e
    OpenAI (1536 dims) usa coleções docuvector_oai_*.
    Evita o InvalidDimensionException do ChromaDB.
    """

    settings = get_settings()
    is_openai = embedding_provider_name == EmbeddingProviderName.OPENAI.value
    vector_store = _get_oai_original_store() if is_openai else get_vector_store()

    primary = IngestionUseCase(
        document_repository=SqlAlchemyDocumentRepository(session),
        text_splitter=RecursiveSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        ),
        vector_store=vector_store,
        audit_repository=SqlAlchemyAuditRepository(get_session_factory()),
        upload_max_bytes=settings.upload_max_bytes,
    )
    return MultiCollectionIngestionUseCase(
        primary_ingestion=primary,
        primary_vector_store=vector_store,
        compressed_stores=[],  # compressão é 100% sob demanda
        document_repository=SqlAlchemyDocumentRepository(session),
    )


# =============================================================
# Autenticação via esquema Bearer (HTTPBearer)
# =============================================================
# Nome do cookie HttpOnly usado pela camada web (Sprint 5).
# A API REST continua aceitando Authorization: Bearer normalmente;
# o cookie é uma fonte adicional de token para o frontend server-side,
# que não expõe o JWT ao JavaScript (defesa contra XSS).
SESSION_COOKIE_NAME = "access_token"


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """Extrai o token JWT do header Authorization ou, como fallback, do cookie.

    Precedência: header Authorization (clientes de API, Swagger) tem
    prioridade. Cookie HttpOnly atende o frontend web sem expor o token
    ao JS. Um cliente nunca mistura os dois na mesma request.
    """
    if credentials is not None and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None


def require_authenticated_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    token_service: TokenServiceDependency,
    session: SessionDependency,
) -> TokenPayload:
    """Valida o JWT e confirma que o usuário ainda existe no banco.

    A dupla verificação (assinatura JWT + existência no banco) evita
    ForeignKeyViolation quando o banco é resetado durante desenvolvimento
    mas o cookie JWT ainda está ativo no browser.
    """
    token = _extract_token(request, credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = token_service.verify(token)
    except AuthenticationError as authentication_failure:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from authentication_failure

    # Confirma que o usuário ainda existe no banco.
    # Evita ForeignKeyViolation quando o banco é recriado
    # mas o cookie JWT anterior ainda está ativo.
    user_repo = SqlAlchemyUserRepository(session)
    if user_repo.find_by_id(payload.user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


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
