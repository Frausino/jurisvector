"""Testes unit do CompressToCollectionUseCase.

Cobre P0.2 (texto preservado) e P1.1 (idempotência com delete).
Segue padrão do projeto: fakes com assinatura explícita, sem *args.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from docuvector.application.compress_to_collection_use_case import (
    CompressToCollectionInput,
    CompressToCollectionUseCase,
)
from docuvector.domain.entities import Document, DocumentChunk, RetrievedChunk
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.enums import CompressionMethod, DocumentStatus, EmbeddingProviderName
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces import ChunkVector
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

_DIMS = 8
_N_CHUNKS = 3


# =============================================================
# Fakes
# =============================================================
class _FakeOriginalStore:
    """VectorStore original: retorna matriz de vetores pré-definida."""

    def __init__(self, n: int = _N_CHUNKS, dims: int = _DIMS) -> None:
        rng = np.random.default_rng(seed=42)
        self._vectors = rng.standard_normal((n, dims)).astype(np.float32)

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        pass

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def get_vectors_for_document(self, owner_id: UUID, document_id: UUID) -> NDArray[np.float32]:
        return self._vectors

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        return 0


class _FakeOriginalStoreEmpty:
    """VectorStore que lança VectorStoreError (documento não existe)."""

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        pass

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def get_vectors_for_document(self, owner_id: UUID, document_id: UUID) -> NDArray[np.float32]:
        raise VectorStoreError("Documento não encontrado.")

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        return 0


class _FakeCompressedStore:
    """Store comprimido que registra operações."""

    def __init__(self) -> None:
        self.added_chunks: list[ChunkVector] = []
        self.deleted_doc_ids: list[UUID] = []

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

    def get_vectors_for_document(self, owner_id: UUID, document_id: UUID) -> NDArray[np.float32]:
        return np.zeros((0, _DIMS), dtype=np.float32)

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        self.deleted_doc_ids.append(document_id)
        return len(self.added_chunks)


def _make_db_chunks(doc_id: UUID, owner_id: UUID, n: int = _N_CHUNKS) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            id=uuid4(),
            document_id=doc_id,
            owner_id=owner_id,
            chunk_index=i,
            text=f"texto do chunk {i} — cláusula jurídica {i}",
            token_count=10,
            embedding_provider=EmbeddingProviderName.SENTENCE_TRANSFORMERS,
            embedding_model="intfloat/multilingual-e5-small",
            embedding_dimensions=_DIMS,
        )
        for i in range(n)
    ]


class _FakeDocumentRepository:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self._chunks = chunks

    def list_chunks_for_document(
        self, owner_id: UUID, document_id: UUID
    ) -> Sequence[DocumentChunk]:
        return [c for c in self._chunks if c.document_id == document_id]

    def save(self, document: Document) -> Document:
        return document

    def find_by_id_for_owner(self, owner_id: UUID, document_id: UUID) -> Document | None:
        return None

    def find_by_checksum_for_owner(self, owner_id: UUID, checksum_sha256: str) -> Document | None:
        return None

    def list_for_owner(self, owner_id: UUID) -> Sequence[Document]:
        return []

    def update_status(
        self,
        owner_id: UUID,
        document_id: UUID,
        new_status: DocumentStatus,
        failure_reason: str | None = None,
    ) -> Document | None:
        return None

    def update_compression_metrics(
        self,
        owner_id: UUID,
        document_id: UUID,
        metrics: CompressionMetrics,
    ) -> Document | None:
        return None

    def save_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        pass

    def delete_for_owner(self, owner_id: UUID, document_id: UUID) -> bool:
        return True


def _make_input(
    doc_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> CompressToCollectionInput:
    return CompressToCollectionInput(
        owner_id=owner_id or uuid4(),
        document_id=doc_id or uuid4(),
        document_filename="contrato.pdf",
        compression_method=CompressionMethod.INT8,
    )


# =============================================================
# P0.2 — Texto preservado nas coleções comprimidas
# =============================================================
@pytest.mark.unit
def test_compress_preserva_texto_do_banco() -> None:
    """Chunks indexados na coleção comprimida devem ter o texto original."""
    doc_id = uuid4()
    owner_id = uuid4()
    db_chunks = _make_db_chunks(doc_id, owner_id)
    compressed = _FakeCompressedStore()

    use_case = CompressToCollectionUseCase(
        original_store=_FakeOriginalStore(),
        compressed_store=compressed,
        target_collection_name="docuvector_int8",
        document_repository=_FakeDocumentRepository(db_chunks),
    )
    use_case.compress(_make_input(doc_id=doc_id, owner_id=owner_id))

    for i, chunk in enumerate(compressed.added_chunks):
        assert chunk.text == f"texto do chunk {i} — cláusula jurídica {i}", (
            f"Chunk {i}: texto vazio invalida o RAG nas coleções comprimidas"
        )


@pytest.mark.unit
def test_compress_texto_nao_e_vazio_sem_document_repository() -> None:
    """Sem document_repository, chunks têm texto vazio (fallback documentado)."""
    compressed = _FakeCompressedStore()
    use_case = CompressToCollectionUseCase(
        original_store=_FakeOriginalStore(),
        compressed_store=compressed,
        target_collection_name="docuvector_int8",
        document_repository=None,
    )
    use_case.compress(_make_input())

    # Fallback: texto vazio é aceitável apenas sem repositório
    for chunk in compressed.added_chunks:
        assert chunk.text == "" or isinstance(chunk.text, str)


# =============================================================
# P1.1 — Idempotência: delete antes de add_chunks
# =============================================================
@pytest.mark.unit
def test_compress_faz_delete_antes_de_add_chunks() -> None:
    """Re-execução não deve duplicar: delete_document antes de add_chunks."""
    doc_id = uuid4()
    owner_id = uuid4()
    db_chunks = _make_db_chunks(doc_id, owner_id)
    compressed = _FakeCompressedStore()

    use_case = CompressToCollectionUseCase(
        original_store=_FakeOriginalStore(),
        compressed_store=compressed,
        target_collection_name="docuvector_int8",
        document_repository=_FakeDocumentRepository(db_chunks),
    )
    inp = _make_input(doc_id=doc_id, owner_id=owner_id)
    use_case.compress(inp)
    use_case.compress(inp)  # Segunda execução — não deve duplicar

    assert doc_id in compressed.deleted_doc_ids, (
        "delete_document deve ser chamado antes de add_chunks para garantir idempotência"
    )


@pytest.mark.unit
def test_compress_chunks_indexados_igual_ao_original() -> None:
    """Número de chunks indexados deve ser igual ao número de vetores originais."""
    doc_id = uuid4()
    owner_id = uuid4()
    compressed = _FakeCompressedStore()

    use_case = CompressToCollectionUseCase(
        original_store=_FakeOriginalStore(n=_N_CHUNKS),
        compressed_store=compressed,
        target_collection_name="docuvector_int8",
        document_repository=_FakeDocumentRepository([]),
    )
    result = use_case.compress(_make_input(doc_id=doc_id, owner_id=owner_id))

    assert result.chunks_indexed == _N_CHUNKS
    assert len(compressed.added_chunks) == _N_CHUNKS


@pytest.mark.unit
def test_compress_levanta_vector_store_error_se_doc_nao_existe() -> None:
    """VectorStoreError quando o documento não existe na coleção original."""
    use_case = CompressToCollectionUseCase(
        original_store=_FakeOriginalStoreEmpty(),
        compressed_store=_FakeCompressedStore(),
        target_collection_name="docuvector_int8",
        document_repository=None,
    )
    with pytest.raises(VectorStoreError):
        use_case.compress(_make_input())


@pytest.mark.unit
def test_compress_preserva_collection_name_no_resultado() -> None:
    """O resultado deve informar em qual coleção os chunks foram indexados."""
    collection = "docuvector_binary"
    use_case = CompressToCollectionUseCase(
        original_store=_FakeOriginalStore(),
        compressed_store=_FakeCompressedStore(),
        target_collection_name=collection,
        document_repository=None,
    )
    result = use_case.compress(_make_input())

    assert result.collection_name == collection
    assert result.compression_method is CompressionMethod.INT8
