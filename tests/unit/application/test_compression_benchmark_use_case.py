"""Testes unit do Bloco 5 — CompressionBenchmarkUseCase.

Todos os colaboradores são fakes em memória. Nenhum I/O real.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from docuvector.application.compression_benchmark_use_case import (
    BenchmarkInput,
    CompressionBenchmarkUseCase,
    _compute_semantic_retention,
)
from docuvector.domain.entities import (
    AuditEvent,
    Document,
    DocumentChunk,
    RetrievedChunk,
)
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.enums import (
    AuditAction,
    AuditStatus,
    CompressionMethod,
    DocumentStatus,
    FileFormat,
)
from docuvector.domain.exceptions import ResourceNotFoundError, VectorStoreError
from docuvector.domain.interfaces import ChunkVector
from docuvector.domain.interfaces.embedding_provider import (
    EmbeddingVector,
)


# ------------------------------------------------------------------
# Fakes
# ------------------------------------------------------------------
class _FakeDocumentRepository:
    def __init__(self, documents: list[Document]) -> None:
        self._docs = {d.id: d for d in documents}
        self.last_metrics_written: CompressionMetrics | None = None

    def find_by_id_for_owner(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Document | None:
        doc = self._docs.get(document_id)
        if doc is None or doc.owner_id != owner_id:
            return None
        return doc

    def update_compression_metrics(
        self,
        owner_id: UUID,
        document_id: UUID,
        metrics: CompressionMetrics,
    ) -> Document | None:
        doc = self.find_by_id_for_owner(owner_id, document_id)
        if doc is None:
            return None

        self.last_metrics_written = metrics

        updated = replace(
            doc,
            compression_method=metrics.method,
        )

        self._docs[document_id] = updated
        return updated

    def save(self, doc: Document) -> Document:
        return doc

    def find_by_checksum_for_owner(
        self,
        owner_id: UUID,
        checksum_sha256: str,
    ) -> Document | None:
        return None

    def list_for_owner(
        self,
        owner_id: UUID,
    ) -> Sequence[Document]:
        return []

    def update_status(
        self,
        owner_id: UUID,
        document_id: UUID,
        new_status: DocumentStatus,
        failure_reason: str | None = None,
    ) -> Document | None:
        return None

    def delete_for_owner(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> bool:
        return False

    def save_chunks(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        return None

    def list_chunks_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Sequence[DocumentChunk]:
        return []


class _FakeVectorStore:
    def __init__(
        self,
        matrix: np.ndarray,
        owner_id: UUID,
        document_id: UUID,
    ) -> None:
        self._matrix = matrix
        self._owner = owner_id
        self._doc = document_id

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> np.ndarray:
        if owner_id != self._owner or document_id != self._doc:
            raise VectorStoreError("Documento não encontrado.")
        return self._matrix

    def add_chunks(
        self,
        chunks: Sequence[ChunkVector],
    ) -> None:
        return None

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        return []

    def delete_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> int:
        return 0


class _FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        return []


def _make_document(owner_id: UUID) -> Document:
    return Document(
        owner_id=owner_id,
        filename="contrato.pdf",
        file_format=FileFormat.PDF,
        size_bytes=1024,
        checksum_sha256="abc123",
    )


def _random_matrix(n: int = 20, d: int = 64, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed=seed)
    return rng.standard_normal((n, d)).astype(np.float32)


def _build_use_case(
    owner_id: UUID,
    doc: Document,
    matrix: np.ndarray,
) -> tuple[CompressionBenchmarkUseCase, _FakeDocumentRepository, _FakeAuditRepository]:
    doc_repo = _FakeDocumentRepository([doc])
    vector_store = _FakeVectorStore(matrix, owner_id, doc.id)
    audit_repo = _FakeAuditRepository()
    use_case = CompressionBenchmarkUseCase(
        document_repository=doc_repo,
        vector_store=vector_store,
        audit_repository=audit_repo,
    )
    return use_case, doc_repo, audit_repo


# ------------------------------------------------------------------
# Testes do fluxo feliz
# ------------------------------------------------------------------
@pytest.mark.unit
class TestCompressionBenchmarkUseCaseFluxoFeliz:
    def test_retorna_quatro_resultados(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        use_case, _, _ = _build_use_case(owner, doc, _random_matrix(n=30, d=64))

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        assert len(results) == 4

    def test_resultados_ordenados_por_retention_desc(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        use_case, _, _ = _build_use_case(owner, doc, _random_matrix(n=30, d=64))

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        retentions = [r.semantic_retention for r in results]
        assert retentions == sorted(retentions, reverse=True)

    def test_retention_em_0_a_1(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        use_case, _, _ = _build_use_case(owner, doc, _random_matrix(n=30, d=64))

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        for r in results:
            assert 0.0 <= r.semantic_retention <= 1.0

    def test_best_gravado_no_repositorio(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        use_case, doc_repo, _ = _build_use_case(owner, doc, _random_matrix(n=30, d=64))

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        best = max(results, key=lambda r: r.semantic_retention)
        assert doc_repo.last_metrics_written is not None
        assert doc_repo.last_metrics_written.method == best.method

    def test_audit_emitido_com_metadata_correto(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        use_case, _, audit_repo = _build_use_case(owner, doc, _random_matrix(n=30, d=64))

        use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        audit_events = [
            e
            for e in audit_repo.events
            if e.action is AuditAction.DOCUMENT_UPDATED and e.status is AuditStatus.SUCCESS
        ]
        assert len(audit_events) == 1
        metadata = audit_events[0].metadata
        assert metadata is not None
        assert metadata["benchmark_type"] == "compression"
        assert metadata["compressors_tested"] == 4

    def test_target_dim_customizado_aplicado(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        matrix = _random_matrix(n=30, d=64)
        use_case, _, _ = _build_use_case(owner, doc, matrix)

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id, target_dim=16))

        # PCA e RP devem ter compressed_dim = 16; Int8/Binary preservam dim
        pca_result = next(r for r in results if r.method is CompressionMethod.PCA)
        assert pca_result.compressed_dim == 16

    def test_target_dim_default_e_metade_original(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        matrix = _random_matrix(n=30, d=64)
        use_case, _, _ = _build_use_case(owner, doc, matrix)

        results = use_case.run(
            BenchmarkInput(
                owner_id=owner,
                document_id=doc.id,
            )
        )

        pca_result = next(r for r in results if r.method is CompressionMethod.PCA)

        expected_dim = min(
            matrix.shape[1] // 2,
            matrix.shape[0] - 1,
            matrix.shape[1] - 1,
        )

        assert pca_result.original_dim == 64
        assert pca_result.compressed_dim == expected_dim


# ------------------------------------------------------------------
# Testes de borda e erros
# ------------------------------------------------------------------
@pytest.mark.unit
class TestCompressionBenchmarkUseCaseBordas:
    def test_documento_nao_encontrado_levanta_resource_not_found(self) -> None:
        owner = uuid4()
        doc_repo = _FakeDocumentRepository([])  # repositório vazio
        use_case = CompressionBenchmarkUseCase(
            document_repository=doc_repo,
            vector_store=_FakeVectorStore(_random_matrix(), owner, uuid4()),
            audit_repository=_FakeAuditRepository(),
        )

        with pytest.raises(ResourceNotFoundError):
            use_case.run(BenchmarkInput(owner_id=owner, document_id=uuid4()))

    def test_sem_vetores_levanta_vector_store_error(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)

        class _EmptyVectorStore:
            def get_vectors_for_document(
                self,
                owner_id: UUID,
                document_id: UUID,
            ) -> np.ndarray:
                raise VectorStoreError("Sem vetores.")

            def add_chunks(
                self,
                chunks: Sequence[ChunkVector],
            ) -> None:
                return None

            def search(
                self,
                owner_id: UUID,
                query_embedding: EmbeddingVector,
                top_k: int,
                similarity_threshold: float,
            ) -> Sequence[RetrievedChunk]:
                return []

            def delete_document(
                self,
                owner_id: UUID,
                document_id: UUID,
            ) -> int:
                return 0

        use_case = CompressionBenchmarkUseCase(
            document_repository=_FakeDocumentRepository([doc]),
            vector_store=_EmptyVectorStore(),
            audit_repository=_FakeAuditRepository(),
        )

        with pytest.raises(VectorStoreError):
            use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

    def test_compressor_com_falha_nao_aborta_os_demais(self) -> None:
        """Se um compressor falhar (ex.: target_dim > n_samples), os outros continuam."""
        owner = uuid4()
        doc = _make_document(owner)
        # Matriz pequena: n=5 amostras, d=64 dims.
        # Com target_dim default (32), PCA exige n_samples >= target_dim.
        # n=5 < 32 → PCA falha. Os outros 3 (RP pode falhar tbm, Int8/Binary ok).
        matrix = _random_matrix(n=5, d=64)
        use_case, _, _ = _build_use_case(owner, doc, matrix)

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        # No mínimo Int8 e Binary devem ter passado
        assert len(results) >= 2
        methods = {r.method for r in results}
        assert CompressionMethod.INT8 in methods
        assert CompressionMethod.BINARY in methods

    def test_space_savings_positivo_para_compressores_que_reduzem(self) -> None:
        owner = uuid4()
        doc = _make_document(owner)
        use_case, _, _ = _build_use_case(owner, doc, _random_matrix(n=30, d=64))

        results = use_case.run(BenchmarkInput(owner_id=owner, document_id=doc.id))

        for r in results:
            # Todos os compressores economizam bytes vs float32 original
            assert r.space_savings_pct > 0.0


# ------------------------------------------------------------------
# Testes unit de _compute_semantic_retention
# ------------------------------------------------------------------
@pytest.mark.unit
class TestComputeSemanticRetention:
    def test_vetores_identicos_retornam_1(self) -> None:
        x = _random_matrix(n=10, d=32)
        retention = _compute_semantic_retention(x, x.copy())
        assert retention == pytest.approx(1.0, abs=1e-5)

    def test_resultado_entre_0_e_1(self) -> None:
        x = _random_matrix(n=10, d=32)
        x_compressed = _random_matrix(n=10, d=16, seed=99)
        retention = _compute_semantic_retention(x, x_compressed)
        assert 0.0 <= retention <= 1.0

    def test_vetor_unico_retorna_1(self) -> None:
        """Com apenas 1 vetor não há pares; deve retornar 1.0 por convenção."""
        x = _random_matrix(n=1, d=32)
        assert _compute_semantic_retention(x, x) == pytest.approx(1.0)

    def test_sampling_aplicado_para_n_grande(self) -> None:
        """Com n=30, n_pairs=435 > max_pairs=10 → amostragem ativa."""
        x = _random_matrix(n=30, d=32)
        x_c = _random_matrix(n=30, d=16, seed=7)
        retention = _compute_semantic_retention(x, x_c, max_pairs=10)
        assert 0.0 <= retention <= 1.0

    @given(
        n=st.integers(min_value=2, max_value=30),
        d=st.integers(min_value=4, max_value=64),
    )
    @settings(max_examples=60)
    def test_invariante_range_0_a_1(self, n: int, d: int) -> None:
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        x_c = rng.standard_normal((n, max(1, d // 2))).astype(np.float32)
        retention = _compute_semantic_retention(x, x_c)
        assert 0.0 <= retention <= 1.0
