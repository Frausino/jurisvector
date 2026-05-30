"""Detecção de formato de arquivo a partir do conteúdo real.

Não confiar em `Content-Type` enviado pelo cliente HTTP é defesa
básica: o atacante controla esse header. Validamos pelo conteúdo:

- PDF tem magic bytes `%PDF-` no início (assinatura padrão).
- TXT e MD não têm magic bytes; usamos heurística de "parece texto"
  combinada com a extensão declarada no upload.

Decisão consciente: NÃO usar `python-magic`. Requer libmagic nativa,
que tem instalação complicada no Windows. Heurística manual cobre
os 3 formatos suportados sem dependência extra.
"""

from __future__ import annotations

from docuvector.domain.enums import FileFormat
from docuvector.domain.exceptions import UnsupportedFileFormatError

_ASCII_CONTROL_CHARACTER_LIMIT = 32
_PDF_MAGIC = b"%PDF-"
_TEXT_SAMPLE_BYTES = 1024
_MAX_CONTROL_CHAR_RATIO = 0.05
_ALLOWED_CONTROL_CHARS = frozenset({"\n", "\r", "\t"})


def detect_file_format(content: bytes, declared_filename: str) -> FileFormat:
    """Detecta o formato real do arquivo a partir do conteúdo.

    O `declared_filename` é usado APENAS para distinguir TXT de MD
    (ambos são texto puro); o tipo real (texto vs binário) é validado
    pelo conteúdo. Não permite escolher PDF apenas pelo nome.
    """
    if not content:
        raise UnsupportedFileFormatError("Arquivo vazio.")

    if content.startswith(_PDF_MAGIC):
        return FileFormat.PDF

    if not _looks_like_text(content):
        raise UnsupportedFileFormatError("Formato não reconhecido. Aceitos: PDF, TXT, MD.")

    extension = _extract_extension(declared_filename)
    if extension == "txt":
        return FileFormat.TXT
    if extension in {"md", "markdown"}:
        return FileFormat.MD

    extension_name = extension or "sem extensão"

    raise UnsupportedFileFormatError(
        f"Texto plano sem extensão reconhecida (.txt ou .md). Recebido: '{extension_name}'."
    )


def _looks_like_text(content: bytes) -> bool:
    """Heurística para distinguir texto plano de binário.

    Critério: amostra inicial decodifica em UTF-8 ou latin-1 sem conter
    mais que 5% de caracteres de controle não-whitespace. Cobre TXT/MD
    em qualquer codificação razoável sem falsos positivos em binários.
    """
    sample = content[:_TEXT_SAMPLE_BYTES]
    decoded_sample = _decode_sample(sample)
    if decoded_sample is None or not decoded_sample:
        return False

    control_character_count = sum(
        1
        for character in decoded_sample
        if (
            ord(character) < _ASCII_CONTROL_CHARACTER_LIMIT
            and character not in _ALLOWED_CONTROL_CHARS
        )
    )
    control_character_ratio = control_character_count / len(decoded_sample)
    return control_character_ratio < _MAX_CONTROL_CHAR_RATIO


def _decode_sample(sample: bytes) -> str | None:
    """Tenta UTF-8, depois latin-1. latin-1 nunca falha em bytes válidos."""
    try:
        return sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return sample.decode("latin-1")
        except UnicodeDecodeError:
            return None


def _extract_extension(filename: str) -> str:
    """Devolve a extensão em lowercase sem o ponto, ou string vazia."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", maxsplit=1)[-1].lower()
