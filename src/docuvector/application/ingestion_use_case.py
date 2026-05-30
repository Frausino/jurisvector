"""Caso de uso de ingestão de documentos.

Orquestra o pipeline RAG ponta a ponta:

    upload bytes
        |
        v
    [1] calcular SHA-256 e checar dedup por (owner_id, checksum)
        |
        v
    [2] persistir Document como UPLOADED
        |
        v
    [3] EXTRACTING -> extrair texto (extractor por FileFormat)
        |
        v
    [4] CHUNKING -> dividir em chunks (splitter)
        |
        v
    [5] EMBEDDING -> gerar vetores em batch (embedder escolhido pelo usuário)
        |
        v
    [6] persistir DocumentChunk no banco e vetores no VectorStore
        |
        v
    [7] marcar como EMBEDDED + audit log
        |
        v
    Document pronto para retrieval.

Falha em qualquer passo move o status para FAILED com `failure_reason`
clara e levanta a exceção apropriada para o router HTTP. O upload já
persistido permite ao usuário ver o erro e tentar reupload.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from docuvector.domain.entities import AuditEvent, Document, DocumentChunk
from docuvector.domain.enums import (
    AuditAction,
    AuditStatus,
    DocumentStatus,
    EmbeddingProviderName,
    FileFormat,
)
from docuvector.domain.exceptions import (
    DocumentExtractionError,
    DocumentTooLargeError,
    DocuvectorError,
    EmbeddingGenerationError,
    UnsupportedFileFormatError,
    VectorStoreError,
)
from docuvector.domain.interfaces import (
    AuditRepository,
    ChunkVector,
    DocumentRepository,
    EmbeddingProvider,
    TextSplitter,
    VectorStore,
)
from docuvector.infrastructure.extractors.factory import resolve_extractor
from docuvector.infrastructure.extractors.file_format_detector import detect_file_format

logger = logging.getLogger(__name__)

_AVERAGE_CHARS_PER_TOKEN = 4
_RESOURCE_TYPE = "document"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Retorno do `ingest`. Sinaliza se foi processamento novo ou cache hit."""

    document: Document
    chunks_created: int
    embedding_provider: EmbeddingProviderName
    was_already_ingested: bool


class IngestionUseCase:
    """Pipeline completo de ingestão de um documento."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        text_splitter: TextSplitter,
        vector_store: VectorStore,
        audit_repository: AuditRepository,
        upload_max_bytes: int,
    ) -> None:
        self._documents = document_repository
        self._splitter = text_splitter
        self._vector_store = vector_store
        self._audit = audit_repository
        self._upload_max_bytes = upload_max_bytes

    def ingest(
        self,
        owner_id: UUID,
        filename: str,
        content: bytes,
        embedding_provider: EmbeddingProvider,
        client_ip: str | None,
        user_agent: str | None,
    ) -> IngestionResult:
        """Ingere um documento e retorna o resultado.

        `embedding_provider` é passado pelo caller (resolvido pela
        factory a partir da escolha do usuário). Isso permite que dois
        documentos do mesmo dono usem providers diferentes, o que
        habilita o benchmark da Sprint 4.
        """
        self._enforce_size_limit(content)
        file_format = detect_file_format(content, filename)
        checksum = self._checksum_sha256(content)

        existing_document = self._documents.find_by_checksum_for_owner(owner_id, checksum)
        if existing_document is not None:
            return IngestionResult(
                document=existing_document,
                chunks_created=0,
                embedding_provider=embedding_provider.provider_name,
                was_already_ingested=True,
            )

        persisted_document = self._persist_initial_document(
            owner_id=owner_id,
            filename=filename,
            file_format=file_format,
            size_bytes=len(content),
            checksum=checksum,
        )

        try:
            extracted_text = self._extract(persisted_document, file_format, content)
            chunk_texts = self._split(persisted_document, extracted_text)
            chunks_created = self._embed_and_store(
                document=persisted_document,
                chunk_texts=chunk_texts,
                embedding_provider=embedding_provider,
            )
        except DocuvectorError as ingestion_failure:
            self._mark_as_failed(persisted_document, str(ingestion_failure))
            raise

        finalized_document = self._mark_as_embedded(persisted_document)
        self._audit_success(
            document=finalized_document,
            chunks_created=chunks_created,
            embedding_provider=embedding_provider,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        return IngestionResult(
            document=finalized_document,
            chunks_created=chunks_created,
            embedding_provider=embedding_provider.provider_name,
            was_already_ingested=False,
        )

    # -------------------------------------------------------------
    # Etapas do pipeline (mantidas privadas)
    # -------------------------------------------------------------
    def _enforce_size_limit(self, content: bytes) -> None:
        if len(content) > self._upload_max_bytes:
            raise DocumentTooLargeError(
                f"Arquivo excede o limite de {self._upload_max_bytes} bytes."
            )
        if not content:
            raise UnsupportedFileFormatError("Arquivo vazio.")

    @staticmethod
    def _checksum_sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _persist_initial_document(
        self,
        owner_id: UUID,
        filename: str,
        file_format: FileFormat,
        size_bytes: int,
        checksum: str,
    ) -> Document:
        initial_document = Document(
            owner_id=owner_id,
            filename=filename,
            file_format=file_format,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            status=DocumentStatus.UPLOADED,
        )
        return self._documents.save(initial_document)

    def _extract(
        self,
        document: Document,
        file_format: FileFormat,
        content: bytes,
    ) -> str:
        self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.EXTRACTING,
        )
        extractor = resolve_extractor(file_format)
        extracted_text = extractor.extract(content)
        if not extracted_text.strip():
            raise DocumentExtractionError("Texto extraído está vazio (PDF escaneado sem OCR?).")
        self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.EXTRACTED,
        )
        return extracted_text

    def _split(self, document: Document, text: str) -> list[str]:
        self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.CHUNKING,
        )
        chunk_texts = list(self._splitter.split(text))
        if not chunk_texts:
            raise DocumentExtractionError(
                "Splitter não produziu chunks; texto pode ser muito curto ou degenerado."
            )
        self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.CHUNKED,
        )
        return chunk_texts

    def _embed_and_store(
        self,
        document: Document,
        chunk_texts: list[str],
        embedding_provider: EmbeddingProvider,
    ) -> int:
        self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.EMBEDDING,
        )

        vectors = embedding_provider.embed_passages(chunk_texts)
        if len(vectors) != len(chunk_texts):
            raise EmbeddingGenerationError(
                f"Embedder retornou {len(vectors)} vetores para {len(chunk_texts)} chunks."
            )

        chunk_entities, chunk_vectors = self._build_chunks_and_vectors(
            document=document,
            chunk_texts=chunk_texts,
            vectors=vectors,
            embedding_provider=embedding_provider,
        )

        self._documents.save_chunks(chunk_entities)
        try:
            self._vector_store.add_chunks(chunk_vectors)
        except VectorStoreError:
            logger.exception("vector_store_add_failed", extra={"document_id": str(document.id)})
            raise

        return len(chunk_entities)

    @staticmethod
    def _build_chunks_and_vectors(
        document: Document,
        chunk_texts: list[str],
        vectors: Sequence[Sequence[float]],
        embedding_provider: EmbeddingProvider,
    ) -> tuple[list[DocumentChunk], list[ChunkVector]]:
        chunk_entities: list[DocumentChunk] = []
        chunk_vectors: list[ChunkVector] = []
        for chunk_index, (text, vector) in enumerate(zip(chunk_texts, vectors, strict=True)):
            estimated_token_count = max(1, len(text) // _AVERAGE_CHARS_PER_TOKEN)
            chunk_entity = DocumentChunk(
                document_id=document.id,
                owner_id=document.owner_id,
                chunk_index=chunk_index,
                text=text,
                token_count=estimated_token_count,
                embedding_provider=embedding_provider.provider_name,
                embedding_model=embedding_provider.model_name,
                embedding_dimensions=embedding_provider.dimensions,
            )
            chunk_entities.append(chunk_entity)
            chunk_vectors.append(
                ChunkVector(
                    chunk_id=chunk_entity.id,
                    document_id=document.id,
                    owner_id=document.owner_id,
                    chunk_index=chunk_index,
                    text=text,
                    embedding=tuple(vector),
                    document_filename=document.filename,
                )
            )
        return chunk_entities, chunk_vectors

    def _mark_as_embedded(self, document: Document) -> Document:
        finalized = self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.EMBEDDED,
        )
        if finalized is None:
            raise DocuvectorError("Documento sumiu durante a finalização da ingestão.")
        return finalized

    def _mark_as_failed(self, document: Document, reason: str) -> None:
        self._documents.update_status(
            owner_id=document.owner_id,
            document_id=document.id,
            new_status=DocumentStatus.FAILED,
            failure_reason=reason,
        )

    def _audit_success(
        self,
        document: Document,
        chunks_created: int,
        embedding_provider: EmbeddingProvider,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self._audit.append(
            AuditEvent(
                actor_user_id=document.owner_id,
                action=AuditAction.DOCUMENT_UPLOADED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=document.id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={
                    "filename": document.filename,
                    "file_format": document.file_format.value,
                    "size_bytes": document.size_bytes,
                    "chunks_created": chunks_created,
                    "embedding_provider": embedding_provider.provider_name.value,
                    "embedding_model": embedding_provider.model_name,
                    "embedding_dimensions": embedding_provider.dimensions,
                    "ingest_completed_at": int(time.time()),
                },
            )
        )
