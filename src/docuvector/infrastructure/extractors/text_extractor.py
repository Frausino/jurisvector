"""Extração de texto cru de arquivos planos (TXT, MD).

Estratégia de decodificação:
1. Tenta UTF-8 estrito (BOM aceito).
2. Fallback para latin-1, que NUNCA falha em bytes válidos. Garante
   que documentos antigos ou de origem Windows-1252 não derrubem o
   pipeline.

Decisão consciente: não usar `chardet`. Adiciona dependência pesada
para um benefício marginal num escopo onde os usuários enviam
majoritariamente UTF-8.
"""

from __future__ import annotations

import codecs

from docuvector.domain.enums import FileFormat
from docuvector.domain.exceptions import DocumentExtractionError

_PLAIN_TEXT_FORMATS: frozenset[FileFormat] = frozenset({FileFormat.TXT, FileFormat.MD})


class PlainTextExtractor:
    """Extrai texto de arquivos TXT e MD.

    Markdown é tratado como texto puro neste estágio: a estrutura de
    cabeçalhos, listas e ênfase é preservada como está e flui para o
    splitter. Não fazemos parsing semântico de Markdown porque o LLM
    final lida bem com a sintaxe nativa.
    """

    def supports(self, file_format: FileFormat) -> bool:
        return file_format in _PLAIN_TEXT_FORMATS

    def extract(self, content: bytes) -> str:
        if not content:
            raise DocumentExtractionError("Arquivo vazio.")

        try:
            return self._decode_utf8(content)
        except UnicodeDecodeError:
            return self._decode_latin1_with_warning_marker(content)

    @staticmethod
    def _decode_utf8(content: bytes) -> str:
        """Decodifica UTF-8 aceitando BOM opcional no início do arquivo."""
        if content.startswith(codecs.BOM_UTF8):
            return content[len(codecs.BOM_UTF8) :].decode("utf-8")
        return content.decode("utf-8")

    @staticmethod
    def _decode_latin1_with_warning_marker(content: bytes) -> str:
        """Decodifica latin-1 como rede de segurança.

        Latin-1 mapeia 1:1 com os 256 primeiros code points Unicode,
        então nunca falha em decode. O resultado pode ter caracteres
        estranhos se o original era outra codificação, mas evita perda
        total de dados.
        """
        return content.decode("latin-1")
