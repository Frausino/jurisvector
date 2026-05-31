"""Testes unit do RetrievalUseCase com fakes em memória."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from docuvector.application.retrieval_use_case import RetrievalUseCase
from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.enums import EmbeddingProviderName
from docuvector.domain.exceptions import ValidationError
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector


# =============================================================
# Fakes
# =============================================================
class _FakeEmbedder:
    """Embedder fake que devolve sempre o mesmo vetor curto."""

    @property
    def provider_name(self) -> EmbeddingProviderName:
        return EmbeddingProviderName.SENTENCE_TRANSFORMERS

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimensions(self) -> int:
        return 4

    def embed_query(self, text: str) -> EmbeddingVector:
        # Vetor determinístico baseado no comprimento do texto.
        return (0.1, 0.2, 0.3, float(len(text) % 10) / 10)

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        return [(0.1, 0.2, 0.3, 0.4) for _ in texts]


class _RecordingVectorStore:
    """Vector store fake que registra a última busca para asserts."""

    def __init__(self, chunks_to_return: Sequence[RetrievedChunk]) -> None:
        self._chunks_to_return = chunks_to_return
        self.last_search_owner: UUID | None = None
        self.last_search_top_k: int | None = None
        self.last_search_threshold: float | None = None

    def add_chunks(self, _chunks) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        self.last_search_owner = owner_id
        self.last_search_top_k = top_k
        self.last_search_threshold = similarity_threshold
        return self._chunks_to_return

    def delete_document(self, _owner_id: UUID, _document_id: UUID) -> int:
        raise NotImplementedError


def _make_chunk(similarity: float = 0.9, index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_filename="contrato.pdf",
        text="texto do trecho",
        similarity=similarity,
        chunk_index=index,
    )


# =============================================================
# Fluxo feliz
# =============================================================
@pytest.mark.unit
def test_retrieve_returns_chunks_from_vector_store() -> None:
    expected_chunks = [_make_chunk(0.95), _make_chunk(0.85, index=1)]
    store = _RecordingVectorStore(expected_chunks)
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=5,
        default_similarity_threshold=0.6,
    )

    result = use_case.retrieve(
        owner_id=uuid4(),
        query="Qual a cláusula de rescisão?",
        embedding_provider=_FakeEmbedder(),
    )

    assert result.chunks == tuple(expected_chunks)
    assert result.query == "Qual a cláusula de rescisão?"


@pytest.mark.unit
def test_retrieve_uses_defaults_when_overrides_not_provided() -> None:
    store = _RecordingVectorStore([])
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=7,
        default_similarity_threshold=0.42,
    )

    use_case.retrieve(
        owner_id=uuid4(),
        query="qualquer pergunta",
        embedding_provider=_FakeEmbedder(),
    )

    assert store.last_search_top_k == 7
    assert store.last_search_threshold == pytest.approx(0.42)


@pytest.mark.unit
def test_retrieve_honors_explicit_overrides() -> None:
    store = _RecordingVectorStore([])
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=5,
        default_similarity_threshold=0.6,
    )

    use_case.retrieve(
        owner_id=uuid4(),
        query="pergunta com overrides",
        embedding_provider=_FakeEmbedder(),
        top_k=3,
        similarity_threshold=0.8,
    )

    assert store.last_search_top_k == 3
    assert store.last_search_threshold == pytest.approx(0.8)


@pytest.mark.unit
def test_retrieve_propagates_owner_id_to_vector_store() -> None:
    """Defesa BOLA: owner_id flui DIRETO para o store."""
    store = _RecordingVectorStore([])
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=5,
        default_similarity_threshold=0.6,
    )
    expected_owner = uuid4()

    use_case.retrieve(
        owner_id=expected_owner,
        query="pergunta arbitrária",
        embedding_provider=_FakeEmbedder(),
    )

    assert store.last_search_owner == expected_owner


@pytest.mark.unit
def test_retrieve_trims_query_whitespace() -> None:
    store = _RecordingVectorStore([])
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=5,
        default_similarity_threshold=0.6,
    )

    result = use_case.retrieve(
        owner_id=uuid4(),
        query="   pergunta com espaços   ",
        embedding_provider=_FakeEmbedder(),
    )

    assert result.query == "pergunta com espaços"


# =============================================================
# Validações de entrada
# =============================================================
@pytest.mark.unit
@pytest.mark.parametrize("invalid_query", ["", "  ", "ab"])
def test_retrieve_rejects_queries_too_short(invalid_query: str) -> None:
    store = _RecordingVectorStore([])
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=5,
        default_similarity_threshold=0.6,
    )

    with pytest.raises(ValidationError):
        use_case.retrieve(
            owner_id=uuid4(),
            query=invalid_query,
            embedding_provider=_FakeEmbedder(),
        )


@pytest.mark.unit
def test_retrieve_rejects_none_query() -> None:
    store = _RecordingVectorStore([])
    use_case = RetrievalUseCase(
        vector_store=store,
        default_top_k=5,
        default_similarity_threshold=0.6,
    )

    with pytest.raises(ValidationError):
        use_case.retrieve(
            owner_id=uuid4(),
            query=None,  # type: ignore[arg-type]
            embedding_provider=_FakeEmbedder(),
        )
