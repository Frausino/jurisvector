"""Contrato de persistência para documentos e chunks.

Todo método que LEIA ou ESCREVA exige `owner_id`. O repositório NÃO
expõe operações cross-owner; isso é defesa contra BOLA no contrato,
não no use case, eliminando uma classe inteira de falhas por esquecimento.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from docuvector.domain.entities import Document, DocumentChunk
from docuvector.domain.enums import DocumentStatus


class DocumentRepository(Protocol):
    """Persistência de documentos com isolamento multi-tenant garantido."""

    def save(self, document: Document) -> Document:
        """Persiste um documento novo ou atualiza um existente."""
        ...

    def find_by_id_for_owner(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Document | None:
        """Devolve o documento se pertencer ao dono; None caso contrário.

        Não levanta exceção quando o documento existe mas é de outro
        dono: a discriminação entre 'não existe' e 'não é seu' é
        responsabilidade do use case (que decide se mascara como 404
        ou autoriza acesso administrativo).
        """
        ...

    def find_by_checksum_for_owner(
        self,
        owner_id: UUID,
        checksum_sha256: str,
    ) -> Document | None:
        """Detecta upload duplicado antes de iniciar extração."""
        ...

    def list_for_owner(self, owner_id: UUID) -> Sequence[Document]:
        """Lista documentos do dono, ordenados por data de criação desc."""
        ...

    def update_status(
        self,
        owner_id: UUID,
        document_id: UUID,
        new_status: DocumentStatus,
        failure_reason: str | None = None,
    ) -> Document | None:
        """Atualiza apenas status + failure_reason de forma idempotente."""
        ...

    def delete_for_owner(self, owner_id: UUID, document_id: UUID) -> bool:
        """Remove documento e seus chunks (CASCADE); devolve sucesso."""
        ...

    def save_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        """Persiste chunks em lote, em uma única transação."""
        ...

    def list_chunks_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> Sequence[DocumentChunk]:
        """Lista chunks de um documento (já filtrado por dono)."""
        ...
