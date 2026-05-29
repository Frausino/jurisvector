"""Endpoints REST do recurso `documents`.

Cobertura desta sprint (Bloco 1):
- `GET  /api/v1/documents`         listagem do dono autenticado
- `GET  /api/v1/documents/{id}`    detalhe do dono autenticado
- `DELETE /api/v1/documents/{id}`  exclusão do dono autenticado

`POST /api/v1/documents` (upload) será adicionado na Sprint 3 quando
o `IngestionUseCase` existir; criar o endpoint agora forçaria stub
que não vale a pena.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from docuvector.api.deps import (
    ClientIpDependency,
    CurrentTokenDependency,
    DocumentCrudUseCaseDependency,
)
from docuvector.api.schemas.documents import DocumentListResponse, DocumentResponse

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar documentos do usuário autenticado",
    description=(
        "Retorna os documentos pertencentes ao dono extraído do token. "
        "Não há vazamento entre usuários: a query no banco já filtra "
        "por owner_id."
    ),
)
def list_documents(
    token_payload: CurrentTokenDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
) -> DocumentListResponse:
    documents = crud_use_case.list_for_owner(token_payload.user_id)
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        total=len(documents),
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalhar documento do usuário autenticado",
    description=(
        "Retorna o documento se pertencer ao dono. Documento de outro "
        "dono devolve 404 (não 403), evitando enumeração de "
        "identificadores entre tenants."
    ),
    responses={404: {"description": "Documento não encontrado."}},
)
def get_document(
    document_id: UUID,
    request: Request,
    token_payload: CurrentTokenDependency,
    client_ip: ClientIpDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
) -> DocumentResponse:
    document = crud_use_case.get_for_owner(
        owner_id=token_payload.user_id,
        document_id=document_id,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    return DocumentResponse.model_validate(document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir documento do usuário autenticado",
    description=(
        "Apaga o documento e seus chunks (CASCADE) se pertencer ao "
        "dono. Mesma política de 404 para documento alheio."
    ),
    responses={404: {"description": "Documento não encontrado."}},
)
def delete_document(
    document_id: UUID,
    request: Request,
    token_payload: CurrentTokenDependency,
    client_ip: ClientIpDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
) -> None:
    crud_use_case.delete_for_owner(
        owner_id=token_payload.user_id,
        document_id=document_id,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
