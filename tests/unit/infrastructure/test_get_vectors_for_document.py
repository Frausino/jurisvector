"""Testes unit do Bloco 3 — VectorStore.get_vectors_for_document.

Usa implementação fake em memória, não ChromaDB real.
O ChromaDB é testado no teste de integração.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
import pytest

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector
from docuvector.domain.interfaces.vector_store import ChunkVector


class _FakeVectorStoreWithVectors:
    """Fake VectorStore que armazena vetores em memória."""

    def __init__(self, stored: dict[tuple[UUID, UUID], np.ndarray]) -> None:
        # chave: (owner_id, document_id)
        self._stored = stored

    def get_vectors_for_document(self, owner_id: UUID, document_id: UUID) -> np.ndarray:
        key = (owner_id, document_id)
        if key not in self._stored:
            raise VectorStoreError(f"Documento {document_id} não encontrado para owner {owner_id}.")
        return self._stored[key]

    # Métodos do Protocol (não usados aqui)
    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None: ...

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        return 0


@pytest.mark.unit
class TestGetVectorsForDocument:
    def _make_matrix(self, n: int = 10, d: int = 64) -> np.ndarray:
        rng = np.random.default_rng(seed=42)
        return rng.standard_normal((n, d)).astype(np.float32)

    def test_retorna_matriz_correta(self) -> None:
        owner = uuid4()
        doc_id = uuid4()
        expected = self._make_matrix(n=10, d=64)
        store = _FakeVectorStoreWithVectors({(owner, doc_id): expected})

        result = store.get_vectors_for_document(owner, doc_id)

        assert result.shape == (10, 64)
        np.testing.assert_array_equal(result, expected)

    def test_retorna_ndarray_float32(self) -> None:
        owner = uuid4()
        doc_id = uuid4()
        matrix = self._make_matrix()
        store = _FakeVectorStoreWithVectors({(owner, doc_id): matrix})

        result = store.get_vectors_for_document(owner, doc_id)

        assert result.dtype == np.float32

    def test_owner_errado_levanta_vector_store_error(self) -> None:
        """BOLA: owner diferente não acessa vetores de outro tenant."""
        owner_correto = uuid4()
        owner_atacante = uuid4()
        doc_id = uuid4()
        store = _FakeVectorStoreWithVectors({(owner_correto, doc_id): self._make_matrix()})

        with pytest.raises(VectorStoreError):
            store.get_vectors_for_document(owner_atacante, doc_id)

    def test_documento_inexistente_levanta_vector_store_error(self) -> None:
        store = _FakeVectorStoreWithVectors({})

        with pytest.raises(VectorStoreError):
            store.get_vectors_for_document(uuid4(), uuid4())

    def test_doc_id_errado_mesmo_owner_levanta_error(self) -> None:
        owner = uuid4()
        doc_real = uuid4()
        doc_falso = uuid4()
        store = _FakeVectorStoreWithVectors({(owner, doc_real): self._make_matrix()})

        with pytest.raises(VectorStoreError):
            store.get_vectors_for_document(owner, doc_falso)
