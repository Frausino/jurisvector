"""Splitter recursivo com overlap para fragmentação de texto.

Algoritmo:
1.  Tenta dividir o texto pelo separador mais "alto" (parágrafo duplo).
2.  Para cada bloco resultante:
    - Se cabe em `chunk_size`, vira um chunk.
    - Caso contrário, sub-divide com o próximo separador (linha,
      sentença, espaço).
3.  Ao final, junta blocos pequenos consecutivos respeitando o limite
    e introduz `chunk_overlap` entre chunks adjacentes.

Inspirado em `RecursiveCharacterTextSplitter` do LangChain, mas
reescrito do zero para evitar dependência e ter controle total sobre
edge cases (texto vazio, texto sem separadores, blocos maiores que
`chunk_size`).
"""

from __future__ import annotations

from collections.abc import Sequence

from docuvector.domain.exceptions import ValidationError

# Ordem de tentativa: do separador mais semântico para o mais granular.
_FALLBACK_SEPARATORS: tuple[str, ...] = (
    "\n\n",  # parágrafo
    "\n",  # linha
    ". ",  # sentença (heurística simples; português aceita)
    " ",  # palavra
    "",  # caractere (último recurso)
)


class RecursiveSplitter:
    """Quebra texto em chunks de até `chunk_size` caracteres com overlap.

    `chunk_size` e `chunk_overlap` são medidos em caracteres, não em
    tokens. Tokenização verdadeira viria de tiktoken, mas adicionaria
    dependência por benefício marginal nesta fase. O `IngestionUseCase`
    pode calcular tokens à parte se precisar.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Sequence[str] = _FALLBACK_SEPARATORS,
    ) -> None:
        if chunk_size <= 0:
            raise ValidationError("`chunk_size` deve ser positivo.")
        if chunk_overlap < 0:
            raise ValidationError("`chunk_overlap` não pode ser negativo.")
        if chunk_overlap >= chunk_size:
            raise ValidationError(
                "`chunk_overlap` deve ser menor que `chunk_size` para evitar loop."
            )

        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = tuple(separators)

    def split(self, text: str) -> Sequence[str]:
        """Devolve os chunks na ordem original do texto."""
        cleaned_text = text.strip()
        if not cleaned_text:
            return []

        atomic_pieces = self._recursive_split(cleaned_text, self._separators)
        return self._merge_with_overlap(atomic_pieces)

    # -------------------------------------------------------------
    # Etapa 1: quebra recursiva em peças <= chunk_size
    # -------------------------------------------------------------
    def _recursive_split(
        self,
        text: str,
        separators: tuple[str, ...],
    ) -> list[str]:
        """Quebra `text` em peças menores ou iguais a `chunk_size`.

        Estratégia recursiva: aplica o primeiro separador, e para cada
        pedaço resultante que ainda exceda `chunk_size`, recorre com os
        separadores remanescentes.
        """
        if len(text) <= self._chunk_size:
            return [text]

        active_separator, remaining_separators = self._pick_separator(separators)
        if active_separator == "":
            # Caractere a caractere é o último recurso: corta em janelas
            # de `chunk_size` puras.
            return self._slice_by_size(text)

        raw_parts = text.split(active_separator)
        pieces: list[str] = []
        for part in raw_parts:
            restored_part = self._restore_separator(part, active_separator, separators)
            if len(restored_part) <= self._chunk_size:
                if restored_part.strip():
                    pieces.append(restored_part)
            else:
                pieces.extend(self._recursive_split(restored_part, remaining_separators))
        return pieces

    @staticmethod
    def _pick_separator(separators: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
        """Devolve (separador atual, separadores restantes)."""
        if not separators:
            return "", ()
        return separators[0], separators[1:]

    @staticmethod
    def _restore_separator(
        piece: str,
        separator: str,
        separators_chain: tuple[str, ...],
    ) -> str:
        """Recoloca o separador no fim do trecho.

        Sem isso, o texto original perde marcação (ex.: ponto final do
        ". " ou quebra de linha). Mantemos a marcação para preservar
        legibilidade dos chunks. Pulamos quando o separador é vazio.
        """
        if not separator:
            return piece
        # Não restauramos no último separador da cadeia (caractere puro).
        if separator == separators_chain[-1]:
            return piece
        return piece + separator if not piece.endswith(separator) else piece

    def _slice_by_size(self, text: str) -> list[str]:
        """Corta texto em janelas de exatamente `chunk_size` caracteres."""
        return [
            text[index : index + self._chunk_size]
            for index in range(0, len(text), self._chunk_size)
        ]

    # -------------------------------------------------------------
    # Etapa 2: junta peças pequenas e aplica overlap
    # -------------------------------------------------------------
    def _merge_with_overlap(self, pieces: Sequence[str]) -> list[str]:
        """Combina peças pequenas em chunks até `chunk_size` e adiciona overlap.

        Sem essa etapa, ficaríamos com muitos chunks minúsculos (cada
        parágrafo um chunk). Com ela, agrupamos parágrafos vizinhos até
        atingir o limite.
        """
        chunks: list[str] = []
        current_buffer: list[str] = []
        current_length = 0

        for piece in pieces:
            piece_length = len(piece)
            projected_length = current_length + piece_length
            buffer_is_not_empty = current_buffer != []

            if projected_length > self._chunk_size and buffer_is_not_empty:
                chunks.append("".join(current_buffer))
                current_buffer, current_length = self._seed_next_buffer(current_buffer)

            current_buffer.append(piece)
            current_length += piece_length

        if current_buffer:
            chunks.append("".join(current_buffer))

        return [chunk.strip() for chunk in chunks if chunk.strip()]

    def _seed_next_buffer(self, previous_buffer: list[str]) -> tuple[list[str], int]:
        """Inicia o próximo buffer com `chunk_overlap` caracteres do final.

        Mantém continuidade semântica entre chunks adjacentes sem
        descer abaixo de zero (evita índices negativos em buffers
        menores que o overlap).
        """
        if self._chunk_overlap == 0:
            return [], 0

        previous_text = "".join(previous_buffer)
        overlap_text = previous_text[-self._chunk_overlap :]
        return [overlap_text], len(overlap_text)
