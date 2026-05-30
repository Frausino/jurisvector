"""Schemas Pydantic para o recurso `documents`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from docuvector.domain.enums import DocumentStatus, EmbeddingProviderName, FileFormat


class DocumentResponse(BaseModel):
    """Representação pública de um documento.

    `failure_reason` é incluído apenas quando o documento está em
    estado FAILED; campos administrativos detalhados (telemetria de
    compressão da Sprint 4) não aparecem aqui.
    """

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    filename: str
    file_format: FileFormat
    size_bytes: int = Field(ge=0)
    status: DocumentStatus
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Envelope da listagem com `items` e `total`.

    Wrap explícito permite paginação no futuro sem quebrar contrato.
    """

    model_config = ConfigDict(frozen=True)

    items: list[DocumentResponse]
    total: int = Field(ge=0)


class DocumentUploadResponse(BaseModel):
    """Resposta do POST /documents.

    Inclui `was_already_ingested` para distinguir um upload real de
    cache hit por checksum (dedup). A UX usa isso para informar o
    usuário que o documento já existia.
    """

    model_config = ConfigDict(frozen=True)

    document: DocumentResponse
    chunks_created: int = Field(ge=0)
    embedding_provider: EmbeddingProviderName
    was_already_ingested: bool


class EmbeddingProviderOption(BaseModel):
    """Item da lista de provedores de embedding disponíveis.

    Usado pela UX para popular o select que o usuário usa ao subir um
    documento. Inclui o nome canônico, o modelo concreto e as dimensões
    para exibição informativa.
    """

    model_config = ConfigDict(frozen=True)

    name: EmbeddingProviderName
    model: str
    dimensions: int
    description: str


class EmbeddingProviderListResponse(BaseModel):
    """Envelope da listagem de provedores disponíveis."""

    model_config = ConfigDict(frozen=True)

    items: list[EmbeddingProviderOption]
    default: EmbeddingProviderName
