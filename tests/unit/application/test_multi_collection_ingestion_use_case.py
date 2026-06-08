"""Testes unit do MultiCollectionIngestionUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from docuvector.application.ingestion_use_case import IngestionResult, IngestionUseCase
from docuvector.application.multi_collection_ingestion_use_case import (
    MultiCollectionIngestionUseCase,
)
from docuvector.domain.entities import Document, DocumentChunk, RetrievedChunk
from docuvector.domain.enums import (
    CompressionMethod,
    DocumentStatus,
    EmbeddingProviderName,
    FileFormat,
)
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces import ChunkVector, DocumentRepository
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

_DIMS = 8


class _FakeEmbedder:
    @property
    def provider_name(self) -> EmbeddingProviderName:
        return EmbeddingProviderName.SENTENCE_TRANSFORMERS

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dimensions(self) -> int:
        return _DIMS

    def embed_query(self, _text: str) -> EmbeddingVector:
        return tuple([0.1] * _DIMS)

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        return [tuple([0.1] * _DIMS) for _ in texts]


# =============================================================
# Fakes
# =============================================================
@dataclass
class _FakePrimaryIngestion:
    """Stub do IngestionUseCase que devolve um resultado configurável."""

    result_to_return: IngestionResult

    def ingest(
        self,
        owner_id: UUID,
        filename: str,
        content: bytes,
        embedding_provider: object,
        client_ip: str | None,
        user_agent: str | None,
    ) -> IngestionResult:
        return self.result_to_return


class _FakeVectorStoreWithVectors:
    """VectorStore que devolve uma matriz de vetores pré-definida."""

    def __init__(self, vectors: NDArray[np.float32]) -> None:
        self._vectors = vectors
        self.added_chunks: list[ChunkVector] = []

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        self.added_chunks.extend(chunks)

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        return self._vectors

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        return 0


class _FailingCompressedStore:
    """Store que sempre falha ao adicionar chunks."""

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        raise VectorStoreError("falha simulada")

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def get_vectors_for_document(self, *_: object, **__: object) -> NDArray[np.float32]:
        return np.zeros((0, _DIMS), dtype=np.float32)

    def delete_document(self, *_: object, **__: object) -> int:
        return 0


class _RecordingCompressedStore:
    """Store que registra os chunks recebidos."""

    def __init__(self) -> None:
        self.added_chunks: list[ChunkVector] = []

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        self.added_chunks.extend(chunks)

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def get_vectors_for_document(self, *_: object, **__: object) -> NDArray[np.float32]:
        return np.zeros((0, _DIMS), dtype=np.float32)

    def delete_document(self, *_: object, **__: object) -> int:
        return 0


class _FakeDocumentRepository:
    def find_by_id_for_owner(self, owner_id: UUID, document_id: UUID) -> Document | None:
        return None

    def save(self, doc: Document) -> Document:
        return doc

    def find_by_checksum_for_owner(self, owner_id: UUID, checksum: str) -> Document | None:
        return None

    def list_for_owner(self, owner_id: UUID) -> Sequence[Document]:
        return []

    def update_status(self, *_: object, **__: object) -> Document | None:
        return None

    def update_compression_metrics(self, *_: object, **__: object) -> Document | None:
        return None

    def delete_for_owner(self, *_: object, **__: object) -> bool:
        return True

    def save_chunks(self, *_: object, **__: object) -> None:
        pass

    def list_chunks_for_document(
        self, owner_id: UUID, document_id: UUID
    ) -> Sequence[DocumentChunk]:
        return []


def _make_document(owner_id: UUID) -> Document:
    return Document(
        owner_id=owner_id,
        filename="contrato.pdf",
        file_format=FileFormat.PDF,
        size_bytes=1024,
        checksum_sha256="abc123",
        status=DocumentStatus.EMBEDDED,
    )


def _make_ingestion_result(was_already_ingested: bool = False) -> IngestionResult:
    owner = uuid4()
    doc = _make_document(owner_id=owner)
    return IngestionResult(
        document=doc,
        chunks_created=0 if was_already_ingested else 4,
        embedding_provider=EmbeddingProviderName.SENTENCE_TRANSFORMERS,
        was_already_ingested=was_already_ingested,
    )


# =============================================================
# Testes
# =============================================================
@pytest.mark.unit
def test_ingest_nao_popula_colecoes_comprimidas() -> None:
    rng = np.random.default_rng(seed=0)
    vectors = rng.standard_normal((4, _DIMS)).astype(np.float32)

    primary_result = _make_ingestion_result()
    primary_store = _FakeVectorStoreWithVectors(vectors)

    int8_store = _RecordingCompressedStore()
    binary_store = _RecordingCompressedStore()

    use_case = MultiCollectionIngestionUseCase(
        primary_ingestion=cast(
            "IngestionUseCase",
            _FakePrimaryIngestion(primary_result),
        ),
        primary_vector_store=primary_store,
        compressed_stores=[
            (CompressionMethod.INT8, int8_store),
            (CompressionMethod.BINARY, binary_store),
        ],
        document_repository=cast(
            "DocumentRepository",
            _FakeDocumentRepository(),
        ),
    )

    result = use_case.ingest(
        owner_id=primary_result.document.owner_id,
        filename="contrato.pdf",
        content=b"conteudo",
        embedding_provider=_FakeEmbedder(),
        client_ip=None,
        user_agent=None,
    )

    assert result.all_collections_succeeded
    assert int8_store.added_chunks == []
    assert binary_store.added_chunks == []


@pytest.mark.unit
def test_ingest_nao_replica_para_colecoes_comprimidas() -> None:
    """Nova arquitetura: ingestão grava apenas na coleção original."""

    rng = np.random.default_rng(seed=1)
    vectors = rng.standard_normal((3, _DIMS)).astype(np.float32)

    primary_result = _make_ingestion_result()
    primary_store = _FakeVectorStoreWithVectors(vectors)

    failing_store = _FailingCompressedStore()

    use_case = MultiCollectionIngestionUseCase(
        primary_ingestion=cast(
            "IngestionUseCase",
            _FakePrimaryIngestion(primary_result),
        ),
        primary_vector_store=primary_store,
        compressed_stores=[
            (CompressionMethod.INT8, failing_store),
        ],
        document_repository=cast(
            "DocumentRepository",
            _FakeDocumentRepository(),
        ),
    )

    result = use_case.ingest(
        owner_id=primary_result.document.owner_id,
        filename="contrato.pdf",
        content=b"conteudo",
        embedding_provider=_FakeEmbedder(),
        client_ip=None,
        user_agent=None,
    )

    assert result.primary_result == primary_result
    assert result.all_collections_succeeded
    assert result.side_collection_errors == ()


@pytest.mark.unit
def test_ingest_skip_colecoes_quando_ja_ingerido() -> None:
    """Documentos já indexados não devem replicar nas coleções comprimidas."""
    primary_result = _make_ingestion_result(was_already_ingested=True)
    recording_store = _RecordingCompressedStore()

    use_case = MultiCollectionIngestionUseCase(
        primary_ingestion=cast("IngestionUseCase", _FakePrimaryIngestion(primary_result)),
        primary_vector_store=_FakeVectorStoreWithVectors(np.zeros((0, _DIMS), dtype=np.float32)),
        compressed_stores=[(CompressionMethod.INT8, recording_store)],
        document_repository=cast("DocumentRepository", _FakeDocumentRepository()),
    )

    result = use_case.ingest(
        owner_id=primary_result.document.owner_id,
        filename="contrato.pdf",
        content=b"conteudo",
        embedding_provider=_FakeEmbedder(),
        client_ip=None,
        user_agent=None,
    )

    assert result.primary_result.was_already_ingested
    assert recording_store.added_chunks == []


@pytest.mark.unit
def test_ingest_retorna_primary_result_inalterado() -> None:
    rng = np.random.default_rng(seed=2)
    vectors = rng.standard_normal((2, _DIMS)).astype(np.float32)
    primary_result = _make_ingestion_result()

    use_case = MultiCollectionIngestionUseCase(
        primary_ingestion=cast("IngestionUseCase", _FakePrimaryIngestion(primary_result)),
        primary_vector_store=_FakeVectorStoreWithVectors(vectors),
        compressed_stores=[],
        document_repository=cast("DocumentRepository", _FakeDocumentRepository()),
    )

    result = use_case.ingest(
        owner_id=primary_result.document.owner_id,
        filename="contrato.pdf",
        content=b"conteudo",
        embedding_provider=_FakeEmbedder(),
        client_ip=None,
        user_agent=None,
    )

    assert result.primary_result is primary_result
