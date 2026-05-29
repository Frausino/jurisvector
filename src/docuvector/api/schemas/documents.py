"""Schemas Pydantic para o recurso `documents`.

Convenção do projeto: schemas de response NUNCA são derivados
diretamente das entidades do domínio. Eles têm forma de saída
explícita, garantindo que mudanças no domínio não vazem por
acidente pela API.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from docuvector.domain.enums import DocumentStatus, FileFormat


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
    """Envelope da listagem.

    Wrap explícito (em vez de devolver array cru) permite evoluir para
    paginação no futuro sem quebrar contrato. Padrão recomendado pela
    OWASP API Security para todas as coleções.
    """

    model_config = ConfigDict(frozen=True)

    items: list[DocumentResponse]
    total: int = Field(ge=0)
