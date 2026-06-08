"""Testes unit do CompressedVectorStore.

Fakes seguem o padrão estabelecido em `test_answer_use_case.py`:
assinatura explícita (sem *args/**kwargs), tipos declarados, sem magic numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.interfaces import ChunkVector
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector
from docuvector.infrastructure.compression.binary_compressor import BinaryCompressor
from docuvector.infrastructure.compression.int8_compressor import Int8Compressor
from docuvector.infrastructure.compression.pca_compressor import PcaCompressor
from docuvector.infrastructure.vector_stores.compressed_vector_store import (
    CompressedVectorStore,
)

_DIMS = 8
_N_CHUNKS = 4


# =============================================================
# Fakes
# =============================================================
class _FakeInnerStore:
    """ChromaVectorStore fake que captura os chunks adicionados e a query usada."""

    def __init__(self) -> None:
        self.added_chunks: list[ChunkVector] = []
        self.last_query_embedding: EmbeddingVector | None = None
        self.search_return: list[RetrievedChunk] = []

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        self.added_chunks.extend(chunks)

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        self.last_query_embedding = query_embedding
        return self.search_return

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        return np.zeros((0, 0), dtype=np.float32)

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        return 0


def _make_chunk_vectors(n: int = _N_CHUNKS, dims: int = _DIMS) -> list[ChunkVector]:
    rng = np.random.default_rng(seed=42)
    vectors = rng.standard_normal((n, dims)).astype(np.float32)
    return [
        ChunkVector(
            chunk_id=uuid4(),
            document_id=uuid4(),
            owner_id=uuid4(),
            chunk_index=i,
            text=f"chunk {i}",
            embedding=tuple(float(v) for v in vectors[i]),
            document_filename="doc.pdf",
        )
        for i in range(n)
    ]


# =============================================================
# add_chunks — compressão aplicada
# =============================================================
@pytest.mark.unit
def test_add_chunks_int8_produz_embeddings_menores_em_bytes() -> None:
    """Int8 deve reduzir os valores para o range [-127, 127]."""
    inner = _FakeInnerStore()
    store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())
    chunks = _make_chunk_vectors()

    store.add_chunks(chunks)

    assert len(inner.added_chunks) == _N_CHUNKS
    for chunk in inner.added_chunks:
        assert all(-127 <= v <= 127 for v in chunk.embedding)


@pytest.mark.unit
def test_add_chunks_binary_produz_embeddings_somente_zero_ou_um() -> None:
    inner = _FakeInnerStore()
    store = CompressedVectorStore(inner_store=inner, compressor=BinaryCompressor())
    chunks = _make_chunk_vectors()

    store.add_chunks(chunks)

    for chunk in inner.added_chunks:
        assert all(v in (0.0, 1.0) for v in chunk.embedding)


@pytest.mark.unit
def test_add_chunks_preserva_metadados_do_chunk() -> None:
    """Metadados (IDs, texto, filename) não devem ser alterados pela compressão."""
    inner = _FakeInnerStore()
    store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())
    original_chunks = _make_chunk_vectors(n=2)

    store.add_chunks(original_chunks)

    for original, compressed in zip(original_chunks, inner.added_chunks, strict=True):
        assert compressed.chunk_id == original.chunk_id
        assert compressed.document_id == original.document_id
        assert compressed.owner_id == original.owner_id
        assert compressed.chunk_index == original.chunk_index
        assert compressed.text == original.text
        assert compressed.document_filename == original.document_filename


@pytest.mark.unit
def test_add_chunks_vazio_nao_chama_inner() -> None:
    inner = _FakeInnerStore()
    store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())

    store.add_chunks([])

    assert inner.added_chunks == []


@pytest.mark.unit
def test_add_chunks_pca_reduz_dimensao() -> None:
    """PCA deve reduzir a dimensão dos embeddings."""
    inner = _FakeInnerStore()
    target_dim = _DIMS // 2
    store = CompressedVectorStore(
        inner_store=inner,
        compressor=PcaCompressor(target_dim=target_dim),
    )
    chunks = _make_chunk_vectors(n=6, dims=_DIMS)

    store.add_chunks(chunks)

    for chunk in inner.added_chunks:
        assert len(chunk.embedding) == target_dim


# =============================================================
# search — query comprimida antes de buscar
# =============================================================
@pytest.mark.unit
def test_search_comprime_query_int8_antes_de_buscar() -> None:
    """A query enviada ao inner store deve ter valores no range int8."""
    inner = _FakeInnerStore()
    store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())
    rng = np.random.default_rng(42)
    query = tuple(float(v) for v in rng.standard_normal(_DIMS).astype(np.float32))

    store.search(
        owner_id=uuid4(),
        query_embedding=query,
        top_k=3,
        similarity_threshold=0.5,
    )

    assert inner.last_query_embedding is not None
    assert all(-127 <= v <= 127 for v in inner.last_query_embedding)


@pytest.mark.unit
def test_search_comprime_query_binary_antes_de_buscar() -> None:
    inner = _FakeInnerStore()
    store = CompressedVectorStore(inner_store=inner, compressor=BinaryCompressor())
    rng = np.random.default_rng(42)
    query = tuple(float(v) for v in rng.standard_normal(_DIMS).astype(np.float32))

    store.search(
        owner_id=uuid4(),
        query_embedding=query,
        top_k=3,
        similarity_threshold=0.5,
    )

    assert inner.last_query_embedding is not None
    assert all(v in (0.0, 1.0) for v in inner.last_query_embedding)


@pytest.mark.unit
def test_search_retorna_resultados_do_inner_store() -> None:
    """CompressedVectorStore não filtra os resultados — delega ao inner."""
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_filename="doc.pdf",
        text="texto de teste",
        similarity=0.85,
        chunk_index=0,
    )
    inner = _FakeInnerStore()
    inner.search_return = [chunk]
    store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())

    results = store.search(
        owner_id=uuid4(),
        query_embedding=tuple([0.1] * _DIMS),
        top_k=5,
        similarity_threshold=0.0,
    )

    assert list(results) == [chunk]


# =============================================================
# delete_document — delega ao inner
# =============================================================
@pytest.mark.unit
def test_delete_document_delega_ao_inner() -> None:
    class _CountingStore(_FakeInnerStore):
        delete_called: bool = False

        def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
            self.delete_called = True
            return 3

    inner = _CountingStore()
    store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())

    result = store.delete_document(owner_id=uuid4(), document_id=uuid4())

    assert result == 3
    assert inner.delete_called
