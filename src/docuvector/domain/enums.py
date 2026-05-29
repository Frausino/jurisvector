"""Enumerações de domínio compartilhadas entre entidades."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """Papéis de autorização do sistema."""

    ADMIN = "admin"
    USER = "user"


class AuditAction(str, Enum):
    """Ações sensíveis registradas no log de auditoria.

    Centralizar como enum evita strings mágicas espalhadas pelo código
    e facilita correlação entre eventos no painel administrativo.
    """

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    USER_SEEDED = "user_seeded"
    ACCESS_DENIED = "access_denied"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_UPDATED = "document_updated"
    QUERY_EXECUTED = "query_executed"


class AuditStatus(str, Enum):
    """Resultado de uma ação auditada.

    `forbidden` diferencia tentativas de acesso indevido (que retornam
    HTTP 404 ao cliente para mascarar existência) de falhas legítimas.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    FORBIDDEN = "forbidden"


class FileFormat(str, Enum):
    """Formatos aceitos para ingestão de documentos.

    Extensão e content-type devem ser validados em conjunto durante o
    upload; apenas a extensão é fonte da verdade aqui (string lowercase
    sem ponto), porque a detecção de MIME real ocorre na camada de
    infraestrutura (não no domínio).
    """

    PDF = "pdf"
    TXT = "txt"
    MD = "md"


class DocumentStatus(str, Enum):
    """Ciclo de vida de um documento no pipeline RAG.

    Transições válidas (não modeladas como máquina de estado formal,
    mas documentadas aqui para o use case respeitar):

        UPLOADED   -> EXTRACTING  -> EXTRACTED
                                  -> FAILED
        EXTRACTED  -> CHUNKING    -> CHUNKED
                                  -> FAILED
        CHUNKED    -> EMBEDDING   -> EMBEDDED
                                  -> FAILED
        FAILED     -> (terminal; reupload exige novo documento)

    Documento em EMBEDDED é o único elegível para retrieval.
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
    """Provedores de embedding suportados.

    Persistir o nome do provedor + modelo + dimensões em cada chunk é
    requisito para a Sprint 4 (benchmark de compressão entre provedores).
    """

    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
