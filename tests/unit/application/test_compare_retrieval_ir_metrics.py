"""Testes unit das métricas IR e do CompareRetrievalUseCase.

Cobre Recall@K, Precision@K, MRR e auditoria.
Segue o padrão do projeto: assinatura explícita, sem *args, constantes nomeadas.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from docuvector.application.compare_retrieval_use_case import (
    CompareRetrievalResult,
    CompareRetrievalUseCase,
    _compute_ir_metrics,
)
from docuvector.domain.entities import AuditEvent, RetrievedChunk
from docuvector.domain.enums import AuditAction, CompressionMethod, EmbeddingProviderName
from docuvector.domain.exceptions import ValidationError
from docuvector.domain.interfaces import ChunkVector
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

_TOP_K = 5
_FAKE_DIMS = 4


# =============================================================
# Fakes
# =============================================================
class _FakeEmbedder:
    @property
    def provider_name(self) -> EmbeddingProviderName:
        return EmbeddingProviderName.SENTENCE_TRANSFORMERS

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dimensions(self) -> int:
        return _FAKE_DIMS

    def embed_query(self, _text: str) -> EmbeddingVector:
        return (0.1, 0.2, 0.3, 0.4)

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        return [(0.1, 0.2, 0.3, 0.4) for _ in texts]


class _FakeVectorStore:
    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        self._chunks = chunks
        self.search_owner: UUID | None = None

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        pass

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        self.search_owner = owner_id
        return list(self._chunks)

    def get_vectors_for_document(self, owner_id: UUID, document_id: UUID) -> NDArray[np.float32]:
        return np.zeros((0, _FAKE_DIMS), dtype=np.float32)

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        return 0


class _FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        return []


def _make_chunk(doc_id: UUID | None = None, similarity: float = 0.90) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id or uuid4(),
        document_filename="doc.pdf",
        text="texto jurídico",
        similarity=similarity,
        chunk_index=0,
    )


# =============================================================
# _compute_ir_metrics — funções puras
# =============================================================
@pytest.mark.unit
def test_ir_metrics_recall_perfeito_quando_mesmos_documentos() -> None:
    doc_id = uuid4()
    chunk = _make_chunk(doc_id=doc_id)
    ground_truth = {str(doc_id)}

    metrics = _compute_ir_metrics(
        retrieved=[chunk],
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.recall_at_k == pytest.approx(1.0)


@pytest.mark.unit
def test_ir_metrics_recall_zero_quando_documentos_diferentes() -> None:
    chunk = _make_chunk()  # doc_id diferente do ground truth
    ground_truth = {str(uuid4())}

    metrics = _compute_ir_metrics(
        retrieved=[chunk],
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.recall_at_k == pytest.approx(0.0)


@pytest.mark.unit
def test_ir_metrics_recall_parcial() -> None:
    """2 de 3 documentos relevantes → Recall@5 = 2/3."""
    doc1, doc2, doc3 = uuid4(), uuid4(), uuid4()
    retrieved = [_make_chunk(doc1), _make_chunk(doc2)]
    ground_truth = {str(doc1), str(doc2), str(doc3)}

    metrics = _compute_ir_metrics(
        retrieved=retrieved,
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.recall_at_k == pytest.approx(2 / 3, abs=1e-4)


@pytest.mark.unit
def test_ir_metrics_precision_at_k() -> None:
    """1 relevante em 5 recuperados → Precision@5 = 1/5."""
    doc_id = uuid4()
    retrieved = [
        _make_chunk(doc_id),  # relevante
        _make_chunk(),
        _make_chunk(),
        _make_chunk(),
        _make_chunk(),
    ]
    ground_truth = {str(doc_id)}

    metrics = _compute_ir_metrics(
        retrieved=retrieved,
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.precision_at_k == pytest.approx(1 / _TOP_K, abs=1e-4)


@pytest.mark.unit
def test_ir_metrics_mrr_primeiro_relevante_na_posicao_1() -> None:
    """Relevante em posição 1 → MRR = 1.0."""
    doc_id = uuid4()
    retrieved = [_make_chunk(doc_id), _make_chunk(), _make_chunk()]
    ground_truth = {str(doc_id)}

    metrics = _compute_ir_metrics(
        retrieved=retrieved,
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.mrr == pytest.approx(1.0)


@pytest.mark.unit
def test_ir_metrics_mrr_primeiro_relevante_na_posicao_2() -> None:
    """Relevante em posição 2 → MRR = 0.5."""
    doc_id = uuid4()
    retrieved = [_make_chunk(), _make_chunk(doc_id), _make_chunk()]
    ground_truth = {str(doc_id)}

    metrics = _compute_ir_metrics(
        retrieved=retrieved,
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.mrr == pytest.approx(0.5)


@pytest.mark.unit
def test_ir_metrics_mrr_zero_quando_nenhum_relevante() -> None:
    retrieved = [_make_chunk(), _make_chunk()]
    ground_truth = {str(uuid4())}

    metrics = _compute_ir_metrics(
        retrieved=retrieved,
        ground_truth_doc_ids=ground_truth,
        top_k=_TOP_K,
    )

    assert metrics.mrr == pytest.approx(0.0)


@pytest.mark.unit
def test_ir_metrics_perfeitas_quando_ground_truth_vazio() -> None:
    """Ground truth vazio → métricas perfeitas (nada a recuperar)."""
    metrics = _compute_ir_metrics(
        retrieved=[_make_chunk()],
        ground_truth_doc_ids=set(),
        top_k=_TOP_K,
    )

    assert metrics.recall_at_k == pytest.approx(1.0)
    assert metrics.precision_at_k == pytest.approx(1.0)
    assert metrics.mrr == pytest.approx(1.0)


# =============================================================
# CompareRetrievalUseCase
# =============================================================
@pytest.mark.unit
def test_compare_retorna_resultado_com_metricas_ir() -> None:
    doc_id = uuid4()
    chunk = _make_chunk(doc_id=doc_id)
    original_store = _FakeVectorStore([chunk])
    int8_store = _FakeVectorStore([chunk])

    use_case = CompareRetrievalUseCase(
        original_store=original_store,
        compressed_stores=[(CompressionMethod.INT8, int8_store)],
    )

    result = use_case.compare(
        owner_id=uuid4(),
        query="Qual o prazo de rescisão?",
        embedding_provider=_FakeEmbedder(),
    )

    assert isinstance(result, CompareRetrievalResult)
    assert result.compressed[0].ir_metrics.recall_at_k == pytest.approx(1.0)
    assert result.compressed[0].ir_metrics.mrr == pytest.approx(1.0)


@pytest.mark.unit
def test_compare_propaga_owner_id_a_todas_as_stores() -> None:
    """owner_id deve chegar a cada store — defesa BOLA."""
    owner = uuid4()
    original_store = _FakeVectorStore([])
    int8_store = _FakeVectorStore([])

    use_case = CompareRetrievalUseCase(
        original_store=original_store,
        compressed_stores=[(CompressionMethod.INT8, int8_store)],
    )
    use_case.compare(
        owner_id=owner,
        query="consulta jurídica válida",
        embedding_provider=_FakeEmbedder(),
    )

    assert original_store.search_owner == owner
    assert int8_store.search_owner == owner


@pytest.mark.unit
def test_compare_emite_audit_quando_repositorio_fornecido() -> None:
    audit = _FakeAuditRepository()
    use_case = CompareRetrievalUseCase(
        original_store=_FakeVectorStore([_make_chunk()]),
        compressed_stores=[(CompressionMethod.INT8, _FakeVectorStore([_make_chunk()]))],
        audit_repository=audit,
    )

    use_case.compare(
        owner_id=uuid4(),
        query="consulta com auditoria habilitada",
        embedding_provider=_FakeEmbedder(),
    )

    assert len(audit.events) == 1
    assert audit.events[0].action is AuditAction.QUERY_EXECUTED
    assert audit.events[0].metadata["benchmark_type"] == "retrieval_comparison"


@pytest.mark.unit
def test_compare_nao_emite_audit_quando_repositorio_none() -> None:
    use_case = CompareRetrievalUseCase(
        original_store=_FakeVectorStore([]),
        compressed_stores=[],
        audit_repository=None,
    )
    # Não deve levantar exceção nem emitir eventos
    use_case.compare(
        owner_id=uuid4(),
        query="consulta sem auditoria",
        embedding_provider=_FakeEmbedder(),
    )


@pytest.mark.unit
def test_compare_levanta_validation_error_para_query_curta() -> None:
    use_case = CompareRetrievalUseCase(
        original_store=_FakeVectorStore([]),
        compressed_stores=[],
    )

    with pytest.raises(ValidationError):
        use_case.compare(
            owner_id=uuid4(),
            query="ab",
            embedding_provider=_FakeEmbedder(),
        )
