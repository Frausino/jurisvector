"""Testes unit do CorpusPcaStore.

Cobre os casos levantados no review:
- pca_hash_changes_when_retrained
- pca_not_fitted_returns_empty_search
- query_projection_dimension
- delete_document_invalidates_model
- explained_variance_ratio_presente
- fit_corpus_levanta_se_buffer_vazio
- search_sem_efeito_colateral (sem fit implícito)
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces import ChunkVector
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector
from docuvector.infrastructure.vector_stores.corpus_pca_store import CorpusPcaStore

_DIMS = 16
_TARGET_DIM = 8
_N_CHUNKS = 10


# =============================================================
# Fakes
# =============================================================
class _RecordingInnerStore:
    """ChromaVectorStore fake que registra todas as operações."""

    def __init__(self) -> None:
        self.added_chunks: list[ChunkVector] = []
        self.deleted_doc_ids: list[UUID] = []
        self.last_query_embedding: EmbeddingVector | None = None

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
        return []

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        return np.zeros((0, _DIMS), dtype=np.float32)

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        self.deleted_doc_ids.append(document_id)
        return 0


def _make_chunks(
    n: int = _N_CHUNKS,
    dims: int = _DIMS,
    owner_id: UUID | None = None,
    doc_id: UUID | None = None,
) -> list[ChunkVector]:
    rng = np.random.default_rng(seed=42)
    vectors = rng.standard_normal((n, dims)).astype(np.float32)
    owner = owner_id or uuid4()
    doc = doc_id or uuid4()
    return [
        ChunkVector(
            chunk_id=uuid4(),
            document_id=doc,
            owner_id=owner,
            chunk_index=i,
            text=f"chunk {i}",
            embedding=tuple(float(v) for v in vectors[i]),
            document_filename="doc.pdf",
        )
        for i in range(n)
    ]


# =============================================================
# fit_corpus
# =============================================================
@pytest.mark.unit
def test_fit_corpus_levanta_se_buffer_vazio() -> None:
    store = CorpusPcaStore(inner_store=_RecordingInnerStore(), target_dim=_TARGET_DIM)

    with pytest.raises(VectorStoreError, match="buffer"):
        store.fit_corpus()


@pytest.mark.unit
def test_fit_corpus_retorna_metadata_com_hash() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    store.add_chunks(_make_chunks())

    metadata = store.fit_corpus()

    assert metadata.model_hash != ""
    assert len(metadata.model_hash) == 64  # SHA-256 hex
    assert metadata.n_samples == _N_CHUNKS
    assert metadata.target_dim == _TARGET_DIM


@pytest.mark.unit
def test_fit_corpus_registra_explained_variance_ratio() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    store.add_chunks(_make_chunks())

    metadata = store.fit_corpus()

    assert 0.0 < metadata.explained_variance_ratio <= 1.0


@pytest.mark.unit
def test_fit_corpus_projeta_para_target_dim() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    store.add_chunks(_make_chunks(dims=_DIMS))

    store.fit_corpus()

    for chunk in inner.added_chunks:
        assert len(chunk.embedding) == _TARGET_DIM


@pytest.mark.unit
def test_fit_corpus_limpa_indice_antes_de_reindexar() -> None:
    """Re-treinamento deve limpar o índice para evitar duplicação."""
    inner = _RecordingInnerStore()
    doc_id = uuid4()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    store.add_chunks(_make_chunks(doc_id=doc_id))

    store.fit_corpus()

    assert doc_id in inner.deleted_doc_ids


# =============================================================
# Não há efeito colateral em search
# =============================================================
@pytest.mark.unit
def test_search_sem_pca_retorna_lista_vazia() -> None:
    """Sem fit_corpus(), search não treina PCA — retorna [] e loga aviso."""
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    store.add_chunks(_make_chunks())

    results = store.search(
        owner_id=uuid4(),
        query_embedding=tuple([0.1] * _DIMS),
        top_k=5,
        similarity_threshold=0.0,
    )

    assert list(results) == []
    # Inner store não deve ter sido chamado (sem efeito colateral)
    assert inner.last_query_embedding is None


@pytest.mark.unit
def test_search_comprime_query_para_target_dim_apos_fit() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    store.add_chunks(_make_chunks(dims=_DIMS))
    store.fit_corpus()

    rng = np.random.default_rng(99)
    query = tuple(float(v) for v in rng.standard_normal(_DIMS).astype(np.float32))
    store.search(
        owner_id=uuid4(),
        query_embedding=query,
        top_k=3,
        similarity_threshold=0.0,
    )

    assert inner.last_query_embedding is not None
    assert len(inner.last_query_embedding) == _TARGET_DIM


# =============================================================
# Hash muda ao retreinar
# =============================================================
@pytest.mark.unit
def test_pca_hash_changes_when_retrained_with_new_data() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)

    chunks_a = _make_chunks()

    store.add_chunks(chunks_a)
    metadata_a = store.fit_corpus()

    # Adiciona novos dados e re-treina
    chunks_b = _make_chunks()
    store.add_chunks(chunks_b)
    metadata_b = store.fit_corpus()

    assert metadata_a.model_hash != metadata_b.model_hash


# =============================================================
# Delete invalida modelo
# =============================================================
@pytest.mark.unit
def test_delete_document_invalida_pca() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    doc_id = uuid4()
    store.add_chunks(_make_chunks(doc_id=doc_id))
    store.fit_corpus()

    assert store.model_metadata is not None

    store.delete_document(owner_id=uuid4(), document_id=doc_id)

    assert store.model_metadata is None


@pytest.mark.unit
def test_delete_remove_chunk_do_buffer() -> None:
    inner = _RecordingInnerStore()
    store = CorpusPcaStore(inner_store=inner, target_dim=_TARGET_DIM)
    doc_id = uuid4()
    store.add_chunks(_make_chunks(doc_id=doc_id))

    store.delete_document(owner_id=uuid4(), document_id=doc_id)

    # Buffer deve estar vazio após deletar o único documento
    assert store._pending == []
