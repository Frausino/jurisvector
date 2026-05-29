"""Extração de texto a partir de PDFs usando `pypdf`.

Motivos para a escolha de `pypdf`:
- Pure Python (sem dependências nativas problemáticas no Windows).
- Não renderiza JavaScript embutido (PDFs maliciosos têm superfície
  de ataque menor do que com `pdfminer.six` ou bibliotecas que
  invocam renderers).
- Mantido ativamente; o sucessor da linha `PyPDF2`.

Não fazemos OCR de PDFs escaneados nesta sprint. Eles seguem para
EMBEDDED com texto possivelmente vazio; o use case de ingestão
deve detectar e marcar como FAILED se o texto extraído for trivial.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

from docuvector.domain.enums import FileFormat
from docuvector.domain.exceptions import DocumentExtractionError

_PAGE_SEPARATOR = "\n\n"


class PyPdfExtractor:
    """Extrai texto de PDFs página a página, juntando com separador duplo.

    PDFs criptografados são rejeitados explicitamente. Aceitar um PDF
    criptografado em ambiente RAG cria risco de processar conteúdo que
    o usuário não pode legitimamente ler.
    """

    def supports(self, file_format: FileFormat) -> bool:
        return file_format is FileFormat.PDF

    def extract(self, content: bytes) -> str:
        if not content:
            raise DocumentExtractionError("Arquivo PDF vazio.")

        reader = self._open_reader(content)
        self._reject_if_encrypted(reader)
        return self._extract_all_pages(reader)

    @staticmethod
    def _open_reader(content: bytes) -> PdfReader:
        """Abre o PDF a partir de bytes, mapeando erros para domínio."""
        try:
            return PdfReader(BytesIO(content), strict=False)
        except PdfReadError as pdf_parse_failure:
            raise DocumentExtractionError(
                f"PDF inválido ou corrompido: {pdf_parse_failure}"
            ) from pdf_parse_failure
        except PyPdfError as pdf_failure:
            raise DocumentExtractionError(f"Falha ao abrir PDF: {pdf_failure}") from pdf_failure

    @staticmethod
    def _reject_if_encrypted(reader: PdfReader) -> None:
        if reader.is_encrypted:
            raise DocumentExtractionError(
                "PDF criptografado não é suportado. Remova a proteção antes de ingerir."
            )

    @staticmethod
    def _extract_all_pages(reader: PdfReader) -> str:
        """Concatena o texto de todas as páginas com separador duplo."""
        extracted_pages: list[str] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except (PdfReadError, PyPdfError, ValueError) as page_failure:
                raise DocumentExtractionError(
                    f"Falha ao extrair texto de página: {page_failure}"
                ) from page_failure
            if page_text.strip():
                extracted_pages.append(page_text)
        return _PAGE_SEPARATOR.join(extracted_pages)
