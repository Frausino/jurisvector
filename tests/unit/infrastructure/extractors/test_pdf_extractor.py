"""Testes unit do PyPdfExtractor.

Usa um PDF real gerado em `tests/fixtures/sample_contract.pdf` para
validar o caminho feliz. Casos de erro são produzidos in-memory.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from docuvector.domain.enums import FileFormat
from docuvector.domain.exceptions import DocumentExtractionError
from docuvector.infrastructure.extractors.pdf_extractor import PyPdfExtractor

_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures"
_SAMPLE_PDF = _FIXTURES_DIR / "sample_contract.pdf"


@pytest.fixture
def extractor() -> PyPdfExtractor:
    return PyPdfExtractor()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    if not _SAMPLE_PDF.exists():
        pytest.skip(f"Fixture PDF não encontrada em {_SAMPLE_PDF}")
    return _SAMPLE_PDF.read_bytes()


@pytest.mark.unit
def test_supports_pdf_only(extractor: PyPdfExtractor) -> None:
    assert extractor.supports(FileFormat.PDF) is True
    assert extractor.supports(FileFormat.TXT) is False
    assert extractor.supports(FileFormat.MD) is False


@pytest.mark.unit
def test_extracts_text_from_valid_pdf(extractor: PyPdfExtractor, sample_pdf_bytes: bytes) -> None:
    extracted = extractor.extract(sample_pdf_bytes)

    assert "Contrato" in extracted
    assert "Clausula" in extracted


@pytest.mark.unit
def test_raises_on_empty_bytes(extractor: PyPdfExtractor) -> None:
    with pytest.raises(DocumentExtractionError, match="vazio"):
        extractor.extract(b"")


@pytest.mark.unit
def test_raises_on_corrupted_pdf(extractor: PyPdfExtractor) -> None:
    """Bytes que não formam um PDF válido devem virar exceção de domínio."""
    garbage = b"This is not a PDF, just plain text bytes that look like garbage."

    with pytest.raises(DocumentExtractionError):
        extractor.extract(garbage)


@pytest.mark.unit
def test_rejects_encrypted_pdf(extractor: PyPdfExtractor, sample_pdf_bytes: bytes) -> None:
    """PDFs criptografados são rejeitados explicitamente.

    Constrói um PDF criptografado em memória a partir do fixture válido.
    """
    writer = PdfWriter(clone_from=BytesIO(sample_pdf_bytes))
    writer.encrypt(user_password="any-password")
    encrypted_buffer = BytesIO()
    writer.write(encrypted_buffer)
    encrypted_bytes = encrypted_buffer.getvalue()

    with pytest.raises(DocumentExtractionError, match="criptografado"):
        extractor.extract(encrypted_bytes)
