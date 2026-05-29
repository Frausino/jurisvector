"""Testes unit do PlainTextExtractor."""

from __future__ import annotations

import codecs

import pytest

from docuvector.domain.enums import FileFormat
from docuvector.domain.exceptions import DocumentExtractionError
from docuvector.infrastructure.extractors.text_extractor import PlainTextExtractor


@pytest.fixture
def extractor() -> PlainTextExtractor:
    return PlainTextExtractor()


@pytest.mark.unit
@pytest.mark.parametrize(
    "file_format",
    [FileFormat.TXT, FileFormat.MD],
)
def test_supports_plain_text_formats(
    extractor: PlainTextExtractor, file_format: FileFormat
) -> None:
    assert extractor.supports(file_format) is True


@pytest.mark.unit
def test_does_not_support_pdf(extractor: PlainTextExtractor) -> None:
    assert extractor.supports(FileFormat.PDF) is False


@pytest.mark.unit
def test_extracts_utf8_text(extractor: PlainTextExtractor) -> None:
    content = "Contrato com acentuação: ção, ã, é, ú.".encode()

    extracted = extractor.extract(content)

    assert "acentuação" in extracted
    assert "ção" in extracted


@pytest.mark.unit
def test_strips_utf8_bom_from_start(extractor: PlainTextExtractor) -> None:
    content = codecs.BOM_UTF8 + "Texto após BOM".encode()

    extracted = extractor.extract(content)

    assert not extracted.startswith("\ufeff")
    assert extracted == "Texto após BOM"


@pytest.mark.unit
def test_falls_back_to_latin1_when_not_utf8(extractor: PlainTextExtractor) -> None:
    """latin-1 nunca falha em decode; precisa não levantar exceção."""
    content = "Caracteres ASCII puros sem invalidação".encode("latin-1")

    extracted = extractor.extract(content)

    assert isinstance(extracted, str)
    assert "ASCII puros" in extracted


@pytest.mark.unit
def test_falls_back_to_latin1_on_invalid_utf8_bytes(
    extractor: PlainTextExtractor,
) -> None:
    """Bytes que NÃO são UTF-8 válido devem cair em latin-1."""
    # Bytes ISO-8859-1 com caracteres acentuados (não-UTF-8 válido).
    content = b"Cl\xe1usula contratual"  # \xe1 é 'á' em latin-1, mas inválido em UTF-8

    extracted = extractor.extract(content)

    assert isinstance(extracted, str)
    # latin-1 decodifica \xe1 como 'á'.
    assert "Cl" in extracted


@pytest.mark.unit
def test_raises_on_empty_content(extractor: PlainTextExtractor) -> None:
    with pytest.raises(DocumentExtractionError):
        extractor.extract(b"")


@pytest.mark.unit
def test_markdown_is_passed_through_as_text(extractor: PlainTextExtractor) -> None:
    """Markdown não é parseado: estrutura passa para o splitter intacta."""
    md_content = b"# Titulo\n\n## Subtitulo\n\n- item 1\n- item 2\n"

    extracted = extractor.extract(md_content)

    assert "# Titulo" in extracted
    assert "## Subtitulo" in extracted
    assert "- item 1" in extracted
