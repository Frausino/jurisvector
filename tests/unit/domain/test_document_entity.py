"""Testes unitários da entidade Document."""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest

from docuvector.domain.entities import Document
from docuvector.domain.enums import DocumentStatus, FileFormat


def _build_document(
    *,
    status: DocumentStatus = DocumentStatus.UPLOADED,
    checksum: str = "a" * 64,
) -> Document:
    """Factory tipada para variar apenas o campo sob teste.

    Existe para evitar dicionário `base_kwargs` que mypy strict não
    consegue casar com a assinatura específica de `Document`.
    """
    return Document(
        owner_id=uuid4(),
        filename="contrato.pdf",
        file_format=FileFormat.PDF,
        size_bytes=1024,
        checksum_sha256=checksum,
        status=status,
    )


@pytest.mark.unit
def test_document_defaults_to_uploaded_status() -> None:
    """Documento recém-criado parte do estado UPLOADED."""
    document = Document(
        owner_id=uuid4(),
        filename="contrato.pdf",
        file_format=FileFormat.PDF,
        size_bytes=1024,
        checksum_sha256="a" * 64,
    )

    assert document.status is DocumentStatus.UPLOADED
    assert document.failure_reason is None


@pytest.mark.unit
def test_document_is_frozen_and_uses_slots() -> None:
    """Document é imutável e não aceita atributos fora dos slots."""
    document = _build_document()

    with pytest.raises(dataclasses.FrozenInstanceError):
        document.filename = "outro.pdf"  # type: ignore[misc]

    # Em Python 3.12, dataclass(frozen=True, slots=True) pode lançar TypeError
    # ao tentar adicionar atributos inexistentes. O requisito é impedir a mutação.
    with pytest.raises((AttributeError, TypeError)):
        document.attribute_inexistente = "valor"  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.parametrize("status", list(DocumentStatus))
def test_is_ready_for_retrieval_only_when_embedded(status: DocumentStatus) -> None:
    """Apenas documentos EMBEDDED participam de queries."""
    document = _build_document(status=status)
    expected = status is DocumentStatus.EMBEDDED

    assert document.is_ready_for_retrieval() is expected


@pytest.mark.unit
def test_is_terminally_failed_only_when_failed() -> None:
    """Estado FAILED é terminal; demais ainda podem progredir."""
    failed_document = _build_document(status=DocumentStatus.FAILED)
    pending_document = _build_document(status=DocumentStatus.EXTRACTING)

    assert failed_document.is_terminally_failed() is True
    assert pending_document.is_terminally_failed() is False
