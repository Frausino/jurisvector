"""Entidades puras de domínio."""

from docuvector.domain.entities.audit_event import AuditEvent
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.entities.document import Document
from docuvector.domain.entities.document_chunk import DocumentChunk
from docuvector.domain.entities.retrieval import Answer, RetrievedChunk
from docuvector.domain.entities.user import User

__all__ = [
    "Answer",
    "AuditEvent",
    "CompressionMetrics",
    "Document",
    "DocumentChunk",
    "RetrievedChunk",
    "User",
]
