"""Interfaces (Protocols) puras da camada de domínio."""

from docuvector.domain.interfaces.audit_repository import AuditRepository
from docuvector.domain.interfaces.document_extractor import DocumentExtractor
from docuvector.domain.interfaces.document_repository import DocumentRepository
from docuvector.domain.interfaces.embedding_provider import (
    EmbeddingProvider,
    EmbeddingVector,
)
from docuvector.domain.interfaces.llm_client import LlmClient, LlmCompletion
from docuvector.domain.interfaces.password_hasher import PasswordHasher
from docuvector.domain.interfaces.text_splitter import TextSplitter
from docuvector.domain.interfaces.token_service import TokenPayload, TokenService
from docuvector.domain.interfaces.user_repository import UserRepository
from docuvector.domain.interfaces.vector_store import ChunkVector, VectorStore

__all__ = [
    "AuditRepository",
    "ChunkVector",
    "DocumentExtractor",
    "DocumentRepository",
    "EmbeddingProvider",
    "EmbeddingVector",
    "LlmClient",
    "LlmCompletion",
    "PasswordHasher",
    "TextSplitter",
    "TokenPayload",
    "TokenService",
    "UserRepository",
    "VectorStore",
]
