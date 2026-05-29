"""Testes unit da factory de extractors."""

from __future__ import annotations

import pytest

from docuvector.domain.enums import FileFormat
from docuvector.infrastructure.extractors.factory import resolve_extractor
from docuvector.infrastructure.extractors.pdf_extractor import PyPdfExtractor
from docuvector.infrastructure.extractors.text_extractor import PlainTextExtractor


@pytest.mark.unit
def test_pdf_format_resolves_to_pypdf_extractor() -> None:
    extractor = resolve_extractor(FileFormat.PDF)
    assert isinstance(extractor, PyPdfExtractor)


@pytest.mark.unit
@pytest.mark.parametrize("file_format", [FileFormat.TXT, FileFormat.MD])
def test_text_formats_resolve_to_plain_text_extractor(
    file_format: FileFormat,
) -> None:
    extractor = resolve_extractor(file_format)
    assert isinstance(extractor, PlainTextExtractor)


@pytest.mark.unit
def test_singleton_returns_same_instance() -> None:
    """A factory mantém singletons; chamadas repetidas devolvem mesma referência."""
    first_call = resolve_extractor(FileFormat.PDF)
    second_call = resolve_extractor(FileFormat.PDF)
    assert first_call is second_call


@pytest.mark.unit
def test_text_extractors_for_txt_and_md_are_the_same_instance() -> None:
    """TXT e MD compartilham extractor (otimização documentada)."""
    txt_extractor = resolve_extractor(FileFormat.TXT)
    md_extractor = resolve_extractor(FileFormat.MD)
    assert txt_extractor is md_extractor
