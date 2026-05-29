"""Roteador entre `FileFormat` e a implementação concreta do extractor.

A factory mantém os extractors como singletons de processo. Eles são
stateless (constroem `PdfReader` ou decodificam bytes sob demanda),
então compartilhar uma instância economiza imports repetidos e mantém
o composition root simples.
"""

from __future__ import annotations

from functools import lru_cache

from docuvector.domain.enums import FileFormat
from docuvector.domain.exceptions import UnsupportedFileFormatError
from docuvector.domain.interfaces import DocumentExtractor
from docuvector.infrastructure.extractors.pdf_extractor import PyPdfExtractor
from docuvector.infrastructure.extractors.text_extractor import PlainTextExtractor


@lru_cache(maxsize=1)
def _build_registry() -> dict[FileFormat, DocumentExtractor]:
    """Constrói a tabela de roteamento uma única vez por processo."""
    plain_text_extractor = PlainTextExtractor()
    return {
        FileFormat.PDF: PyPdfExtractor(),
        FileFormat.TXT: plain_text_extractor,
        FileFormat.MD: plain_text_extractor,
    }


def resolve_extractor(file_format: FileFormat) -> DocumentExtractor:
    """Devolve o extractor responsável pelo formato.

    Levanta `UnsupportedFileFormatError` se o formato não estiver
    mapeado. Acontece quando alguém adiciona um membro a `FileFormat`
    sem registrar implementação aqui.
    """
    registry = _build_registry()
    extractor = registry.get(file_format)
    if extractor is None:
        raise UnsupportedFileFormatError(
            f"Nenhum extractor registrado para o formato {file_format.value!r}."
        )
    return extractor
