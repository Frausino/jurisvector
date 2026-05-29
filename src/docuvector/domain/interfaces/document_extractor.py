"""Contrato para extração de texto a partir de bytes de um arquivo."""

from __future__ import annotations

from typing import Protocol

from docuvector.domain.enums import FileFormat


class DocumentExtractor(Protocol):
    """Extrai texto cru de um documento binário.

    A implementação concreta (pypdf, leitura direta de TXT/MD) vive em
    `infrastructure/extractors/`. O domínio só conhece o contrato.

    `extract` recebe os bytes já lidos pelo upload, evitando que o
    extractor toque no filesystem (mais fácil de testar, mais seguro:
    nenhum extractor escreve em disco arbitrário).
    """

    def supports(self, file_format: FileFormat) -> bool:
        """Indica se este extractor sabe lidar com o formato."""
        ...

    def extract(self, content: bytes) -> str:
        """Devolve o texto cru.

        Implementações DEVEM levantar `DocumentExtractionError` (em
        `domain.exceptions`) ao falhar. Conteúdo malformado é falha
        do upload, não exceção genérica.
        """
        ...
