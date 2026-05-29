"""Implementações concretas de `DocumentExtractor`."""

from docuvector.infrastructure.extractors.factory import resolve_extractor
from docuvector.infrastructure.extractors.pdf_extractor import PyPdfExtractor
from docuvector.infrastructure.extractors.text_extractor import PlainTextExtractor

__all__ = [
    "PlainTextExtractor",
    "PyPdfExtractor",
    "resolve_extractor",
]
