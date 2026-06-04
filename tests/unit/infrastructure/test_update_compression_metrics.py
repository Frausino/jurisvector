"""Testes unit do Bloco 4 — DocumentRepository.update_compression_metrics.

Usa repositório fake em memória. A implementação SQLAlchemy é coberta
pelo teste de integração.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from docuvector.domain.entities import Document
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.enums import (
    CompressionMethod,
    DocumentStatus,
    FileFormat,
)


# ------------------------------------------------------------------
# Fake in-memory DocumentRepository
# ------------------------------------------------------------------
class _FakeDocumentRepository:
    def __init__(self, documents: list[Document]) -> None:
        self._docs = {d.id: d for d in documents}

    def find_by_id_for_owner(self, owner_id: UUID, document_id: UUID) -> Document | None:
        doc = self._docs.get(document_id)
        if doc is None or doc.owner_id != owner_id:
            return None
        return doc

    def update_compression_metrics(
        self, owner_id: UUID, document_id: UUID, metrics: CompressionMetrics
    ) -> Document | None:
        doc = self.find_by_id_for_owner(owner_id, document_id)
        if doc is None:
            return None
        updated = replace(
            doc,
            compression_method=metrics.method,
            original_dimension=metrics.original_dim,
            compressed_dimension=metrics.compressed_dim,
            semantic_retention=metrics.semantic_retention,
            ingest_time_ms=metrics.fit_time_ms + metrics.transform_time_ms,
        )
        self._docs[document_id] = updated
        return updated

    def find_by_checksum_for_owner(
        self,
        owner_id: UUID,
        checksum_sha256: str,
    ) -> Document | None:
        return None

    def update_status(
        self,
        owner_id: UUID,
        document_id: UUID,
        new_status: DocumentStatus,
        failure_reason: str | None = None,
    ) -> Document | None:
        return None

    def list_chunks_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Sequence[object]:
        return []


def _make_document(owner_id: UUID | None = None) -> Document:
    return Document(
        owner_id=owner_id or uuid4(),
        filename="contrato.pdf",
        file_format=FileFormat.PDF,
        size_bytes=1024,
        checksum_sha256="abc123",
    )


def _make_metrics(method: CompressionMethod = CompressionMethod.PCA) -> CompressionMetrics:
    return CompressionMetrics(
        method=method,
        original_dim=384,
        compressed_dim=192,
        bytes_per_element=4.0,
        fit_time_ms=50,
        transform_time_ms=10,
        semantic_retention=0.97,
        n_vectors=20,
    )


@pytest.mark.unit
class TestUpdateCompressionMetrics:
    def test_atualiza_campos_corretamente(self) -> None:
        owner = uuid4()
        doc = _make_document(owner_id=owner)
        repo = _FakeDocumentRepository([doc])
        metrics = _make_metrics()

        updated = repo.update_compression_metrics(owner, doc.id, metrics)

        assert updated is not None
        assert updated.compression_method is CompressionMethod.PCA
        assert updated.original_dimension == 384
        assert updated.compressed_dimension == 192
        assert updated.semantic_retention == pytest.approx(0.97)
        assert updated.ingest_time_ms == 60  # fit(50) + transform(10)

    def test_owner_errado_retorna_none(self) -> None:
        """BOLA: owner diferente não deve atualizar documento de outro tenant."""
        owner_real = uuid4()
        owner_atacante = uuid4()
        doc = _make_document(owner_id=owner_real)
        repo = _FakeDocumentRepository([doc])
        metrics = _make_metrics()

        result = repo.update_compression_metrics(owner_atacante, doc.id, metrics)

        assert result is None
        # Documento original permanece inalterado
        doc_no_repo = repo.find_by_id_for_owner(owner_real, doc.id)
        assert doc_no_repo is not None
        assert doc_no_repo.compression_method is None

    def test_documento_inexistente_retorna_none(self) -> None:
        repo = _FakeDocumentRepository([])
        metrics = _make_metrics()

        result = repo.update_compression_metrics(uuid4(), uuid4(), metrics)

        assert result is None

    def test_persiste_metodo_binary(self) -> None:
        owner = uuid4()
        doc = _make_document(owner_id=owner)
        repo = _FakeDocumentRepository([doc])
        metrics = _make_metrics(method=CompressionMethod.BINARY)

        updated = repo.update_compression_metrics(owner, doc.id, metrics)

        assert updated is not None
        assert updated.compression_method is CompressionMethod.BINARY

    def test_documento_original_permanece_imutavel(self) -> None:
        """Document é frozen: update retorna novo objeto, não modifica o original."""
        owner = uuid4()
        doc = _make_document(owner_id=owner)
        repo = _FakeDocumentRepository([doc])

        repo.update_compression_metrics(owner, doc.id, _make_metrics())

        assert doc.compression_method is None  # original não mudou
