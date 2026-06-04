"""Repositório SQLAlchemy para documentos e chunks.

Todo método filtra por `owner_id`. Não existe método cross-owner aqui;
isolamento multi-tenant é uma propriedade do CONTRATO, não da disciplina
do chamador.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from docuvector.domain.entities import Document, DocumentChunk
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.enums import CompressionMethod, DocumentStatus
from docuvector.infrastructure.persistence.models import (
    DocumentChunkModel,
    DocumentModel,
)


class SqlAlchemyDocumentRepository:
    """Persiste e recupera documentos respeitando multi-tenant."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -------------------------------------------------------------
    # Documents
    # -------------------------------------------------------------
    def save(self, document: Document) -> Document:
        """Insere ou atualiza um documento.

        Política simples: se existe um modelo com o mesmo id, atualiza
        os campos mutáveis; caso contrário, insere. O flush garante que
        defaults (timestamps) do banco voltem para a entidade.
        """
        existing = self._session.get(DocumentModel, document.id)
        if existing is None:
            persistent_document = self._to_model(document)
            self._session.add(persistent_document)
        else:
            self._apply_changes(existing, document)
            persistent_document = existing

        self._session.flush()
        return self._to_entity(persistent_document)

    def find_by_id_for_owner(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Document | None:
        """Localiza um documento pertencente ao dono informado."""
        record = self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id,
                DocumentModel.owner_id == owner_id,
            )
        ).scalar_one_or_none()
        return self._to_entity(record) if record is not None else None

    def find_by_checksum_for_owner(
        self,
        owner_id: UUID,
        checksum_sha256: str,
    ) -> Document | None:
        """Detecta upload duplicado antes de iniciar extração."""
        record = self._session.execute(
            select(DocumentModel).where(
                DocumentModel.owner_id == owner_id,
                DocumentModel.checksum_sha256 == checksum_sha256,
            )
        ).scalar_one_or_none()
        return self._to_entity(record) if record is not None else None

    def list_for_owner(self, owner_id: UUID) -> Sequence[Document]:
        """Documentos do dono, mais recentes primeiro."""
        records = (
            self._session.execute(
                select(DocumentModel)
                .where(DocumentModel.owner_id == owner_id)
                .order_by(DocumentModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [self._to_entity(record) for record in records]

    def update_status(
        self,
        owner_id: UUID,
        document_id: UUID,
        new_status: DocumentStatus,
        failure_reason: str | None = None,
    ) -> Document | None:
        """Atualiza apenas status + failure_reason de forma idempotente."""
        record = self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id,
                DocumentModel.owner_id == owner_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return None

        record.status = new_status
        record.failure_reason = failure_reason
        self._session.flush()
        return self._to_entity(record)

    def update_compression_metrics(
        self,
        owner_id: UUID,
        document_id: UUID,
        metrics: CompressionMetrics,
    ) -> Document | None:
        """Persiste métricas de compressão. Espelha o padrão de update_status."""
        record = self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id,
                DocumentModel.owner_id == owner_id,
            )
        ).scalar_one_or_none()

        if record is None:
            return None

        record.compression_method = metrics.method.value
        record.original_dimension = metrics.original_dim
        record.compressed_dimension = metrics.compressed_dim
        record.semantic_retention = metrics.semantic_retention
        record.ingest_time_ms = int(metrics.fit_time_ms + metrics.transform_time_ms)
        self._session.flush()
        return self._to_entity(record)

    def delete_for_owner(self, owner_id: UUID, document_id: UUID) -> bool:
        """Remove documento e seus chunks (CASCADE)."""
        record = self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id,
                DocumentModel.owner_id == owner_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

    # -------------------------------------------------------------
    # Chunks
    # -------------------------------------------------------------
    def save_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        """Persiste chunks em lote, em uma única transação."""
        models = [self._to_chunk_model(chunk) for chunk in chunks]
        self._session.add_all(models)
        self._session.flush()

    def list_chunks_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Sequence[DocumentChunk]:
        """Lista chunks de um documento, já filtrado por dono."""
        records = (
            self._session.execute(
                select(DocumentChunkModel)
                .where(
                    DocumentChunkModel.document_id == document_id,
                    DocumentChunkModel.owner_id == owner_id,
                )
                .order_by(DocumentChunkModel.chunk_index.asc())
            )
            .scalars()
            .all()
        )
        return [self._to_chunk_entity(record) for record in records]

    # -------------------------------------------------------------
    # Mapping helpers
    # -------------------------------------------------------------
    @staticmethod
    def _to_model(document: Document) -> DocumentModel:
        return DocumentModel(
            id=document.id,
            owner_id=document.owner_id,
            filename=document.filename,
            file_format=document.file_format,
            size_bytes=document.size_bytes,
            checksum_sha256=document.checksum_sha256,
            status=document.status,
            failure_reason=document.failure_reason,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @staticmethod
    def _apply_changes(target: DocumentModel, source: Document) -> None:
        """Aplica mudanças do documento em uma linha já existente."""
        target.filename = source.filename
        target.file_format = source.file_format
        target.size_bytes = source.size_bytes
        target.checksum_sha256 = source.checksum_sha256
        target.status = source.status
        target.failure_reason = source.failure_reason

    @staticmethod
    def _to_entity(record: DocumentModel) -> Document:
        return Document(
            id=record.id,
            owner_id=record.owner_id,
            filename=record.filename,
            file_format=record.file_format,
            size_bytes=record.size_bytes,
            checksum_sha256=record.checksum_sha256,
            status=record.status,
            failure_reason=record.failure_reason,
            created_at=record.created_at,
            updated_at=record.updated_at,
            compression_method=(
                CompressionMethod(record.compression_method)
                if record.compression_method is not None
                else None
            ),
            original_dimension=record.original_dimension,
            compressed_dimension=record.compressed_dimension,
            semantic_retention=(
                float(record.semantic_retention) if record.semantic_retention is not None else None
            ),
            ingest_time_ms=record.ingest_time_ms,
        )

    @staticmethod
    def _to_chunk_model(chunk: DocumentChunk) -> DocumentChunkModel:
        return DocumentChunkModel(
            id=chunk.id,
            document_id=chunk.document_id,
            owner_id=chunk.owner_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            embedding_provider=chunk.embedding_provider,
            embedding_model=chunk.embedding_model,
            embedding_dimensions=chunk.embedding_dimensions,
            created_at=chunk.created_at,
        )

    @staticmethod
    def _to_chunk_entity(record: DocumentChunkModel) -> DocumentChunk:
        return DocumentChunk(
            id=record.id,
            document_id=record.document_id,
            owner_id=record.owner_id,
            chunk_index=record.chunk_index,
            text=record.text,
            token_count=record.token_count,
            embedding_provider=record.embedding_provider,
            embedding_model=record.embedding_model,
            embedding_dimensions=record.embedding_dimensions,
            created_at=record.created_at,
        )
