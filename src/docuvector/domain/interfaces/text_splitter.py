"""Contrato para fragmentar texto em chunks vetorizáveis."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class TextSplitter(Protocol):
    """Quebra um texto em fragmentos sobrepostos para vetorização.

    Implementação padrão (`RecursiveSplitter`) divide por parágrafos,
    depois sentenças, depois palavras, respeitando `chunk_size` e
    `chunk_overlap`. Devolve apenas strings; a montagem dos
    `DocumentChunk` é responsabilidade do use case de ingestão.
    """

    def split(self, text: str) -> Sequence[str]:
        """Devolve a sequência de fragmentos na ordem original."""
        ...
