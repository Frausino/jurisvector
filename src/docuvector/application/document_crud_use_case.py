"""Casos de uso de CRUD de documentos.

Toda operação exige `owner_id` e roteia chamadas para o
`DocumentRepository`, cujo contrato já garante isolamento multi-tenant.
Erros de "não encontrado" e "pertence a outro dono" são mascarados
como o mesmo `ResourceNotFoundError`, mantendo defesa contra
enumeração de identificadores.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from docuvector.domain.entities import AuditEvent, Document
from docuvector.domain.enums import AuditAction, AuditStatus
from docuvector.domain.exceptions import ResourceNotFoundError
from docuvector.domain.interfaces import AuditRepository, DocumentRepository

_RESOURCE_TYPE = "document"


class DocumentCrudUseCase:
    """Operações de leitura e exclusão de documentos do dono autenticado.

    Upload (POST) NÃO entra aqui: a criação envolve pipeline assíncrono
    de ingestão (extract → chunk → embed) e mora em `IngestionUseCase`.
    """

    def __init__(
        self,
        document_repository: DocumentRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._documents = document_repository
        self._audit = audit_repository

    # -------------------------------------------------------------
    # Listagem
    # -------------------------------------------------------------
    def list_for_owner(self, owner_id: UUID) -> Sequence[Document]:
        """Retorna documentos do dono ordenados por data de criação desc.

        Não emite audit log: leitura de catálogo próprio é operação
        rotineira e geraria volume desproporcional. Auditamos apenas
        acesso a recurso específico (get/delete).
        """
        return self._documents.list_for_owner(owner_id)

    # -------------------------------------------------------------
    # Recuperação por id
    # -------------------------------------------------------------
    def get_for_owner(
        self,
        owner_id: UUID,
        document_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> Document:
        """Recupera um documento garantindo que pertence ao dono.

        Levanta `ResourceNotFoundError` se o documento não existe OU
        se existe mas pertence a outro dono. A indistinguibilidade é
        intencional (RGN-10): vazar a existência permitiria enumeração
        de identificadores entre tenants.

        O audit log marca todo acesso negado como FAILURE. Detecção de
        tentativas cross-tenant é tema de auditoria administrativa
        (futura interface dedicada com permissão de admin), não pode
        ser feita aqui sem cruzar a fronteira de ownership do
        repositório.
        """
        document = self._documents.find_by_id_for_owner(owner_id, document_id)
        if document is None:
            self._record_access_denied(
                owner_id=owner_id,
                document_id=document_id,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            raise ResourceNotFoundError("Documento não encontrado.")
        return document

    # -------------------------------------------------------------
    # Exclusão
    # -------------------------------------------------------------
    def delete_for_owner(
        self,
        owner_id: UUID,
        document_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        """Apaga um documento do dono (chunks caem por CASCADE).

        Mesmo comportamento de mascaramento do get: levanta
        ResourceNotFoundError para qualquer cenário de "não pode apagar".
        """
        document = self._documents.find_by_id_for_owner(owner_id, document_id)
        if document is None:
            self._record_access_denied(
                owner_id=owner_id,
                document_id=document_id,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            raise ResourceNotFoundError("Documento não encontrado.")

        self._documents.delete_for_owner(owner_id, document_id)
        self._audit.append(
            AuditEvent(
                actor_user_id=owner_id,
                action=AuditAction.DOCUMENT_DELETED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=document_id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"filename": document.filename},
            )
        )

    # -------------------------------------------------------------
    # Helper privado
    # -------------------------------------------------------------
    def _record_access_denied(
        self,
        owner_id: UUID,
        document_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        """Registra tentativa de acesso a documento inexistente ou alheio.

        Sempre marca como `FAILURE` para preservar anti-enumeração no
        próprio log. A correlação entre eventos suspeitos (mesmo IP,
        múltiplos ids em sequência) é responsabilidade do dashboard
        administrativo, não deste use case.
        """
        self._audit.append(
            AuditEvent(
                actor_user_id=owner_id,
                action=AuditAction.ACCESS_DENIED,
                status=AuditStatus.FAILURE,
                resource_type=_RESOURCE_TYPE,
                resource_id=document_id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"reason": "document_not_accessible"},
            )
        )
