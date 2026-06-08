"""Enumerações de domínio compartilhadas entre entidades."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """Papéis de autorização do sistema."""

    ADMIN = "admin"
    USER = "user"


class AuditAction(str, Enum):
    """Ações sensíveis registradas no log de auditoria."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    USER_SEEDED = "user_seeded"
    USER_REGISTERED = "user_registered"
    USER_CREATED_BY_ADMIN = "user_created_by_admin"
    USER_DELETED = "user_deleted"
    USER_ROLE_CHANGED = "user_role_changed"
    ACCESS_DENIED = "access_denied"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_UPDATED = "document_updated"
    QUERY_EXECUTED = "query_executed"
    RETRIEVAL_COMPARED = "retrieval_compared"
    MULTI_COLLECTION_INGESTED = "multi_collection_ingested"


class AuditStatus(str, Enum):
    """Resultado de uma ação auditada."""

    SUCCESS = "success"
    FAILURE = "failure"
    FORBIDDEN = "forbidden"


class FileFormat(str, Enum):
    """Formatos aceitos para ingestão de documentos."""

    PDF = "pdf"
    TXT = "txt"
    MD = "md"


class DocumentStatus(str, Enum):
    """Ciclo de vida de um documento no pipeline RAG.

    Transições válidas:
        UPLOADED   -> EXTRACTING  -> EXTRACTED   -> FAILED
        EXTRACTED  -> CHUNKING    -> CHUNKED     -> FAILED
        CHUNKED    -> EMBEDDING   -> EMBEDDED    -> FAILED
        FAILED     -> (terminal)
    """

    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    FAILED = "failed"


class EmbeddingProviderName(str, Enum):
    """Provedores de embedding suportados."""

    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class LlmProviderName(str, Enum):
    """Provedores de geração de resposta (LLM) suportados.

    - `OPENAI`: API cloud (gpt-4o-mini etc.). Custo por token, alta qualidade.
    - `OLLAMA`: servidor local (qwen2.5, llama3.2 etc.). Custo zero, sem rede.
    - `MOCK`:   determinístico, para CI/dev offline. Não chama nada externo.
    """

    OPENAI = "openai"
    OLLAMA = "ollama"
    MOCK = "mock"


class CompressionMethod(str, Enum):
    """Métodos de compressão de embeddings suportados pelo benchmark.

    Cada método tem características distintas de trade-off entre
    redução de dimensão/bytes e retenção semântica:

    - PCA: redução de dimensão linear com preservação máxima de variância.
      Requer fit em batch. Melhor retenção semântica na maioria dos casos.
    - RANDOM_PROJECTION: redução de dimensão via matriz aleatória gaussiana.
      Requer fit em batch. Mais rápido que PCA, levemente inferior em retenção.
    - INT8: quantização sem redução de dimensão. 4x menos bytes, quase
      sem perda semântica. Stateless (não precisa de fit).
    - BINARY: quantização extrema. 32x menos bytes teóricos. Perda de
      qualidade visível. Stateless. Útil para filtros aproximados.
    """

    PCA = "pca"
    RANDOM_PROJECTION = "random_projection"
    INT8 = "int8"
    BINARY = "binary"
