"""Schemas Pydantic para o endpoint de benchmark de compressão.

Arquivo separado de `documents.py` por coesão: compressão é uma
feature ortogonal ao CRUD de documentos.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from docuvector.domain.enums import CompressionMethod

_MB: float = 1024.0 * 1024.0


class BenchmarkCompressionRequest(BaseModel):
    """Corpo do POST /api/v1/documents/{id}/benchmark-compression.

    `target_dim` é a dimensão alvo para PCA e RandomProjection.
    Int8 e Binary ignoram este campo (sem redução de dimensão).
    Quando ausente, o use case aplica `original_dim // 2`.
    """

    model_config = ConfigDict(frozen=True)

    target_dim: int | None = Field(
        default=None,
        ge=2,
        description="Dimensão alvo para PCA/RandomProjection. Omitir usa original_dim // 2.",
    )


class CompressorBenchmarkItem(BaseModel):
    """Resultado de um compressor individual."""

    model_config = ConfigDict(frozen=True)

    method: CompressionMethod
    original_dim: int = Field(ge=1)
    compressed_dim: int = Field(ge=1)
    ratio_bytes: float = Field(ge=0.0, description="Ex.: 4.0 = 4x menos bytes.")
    space_savings_pct: float = Field(description="Economia percentual vs original float32.")
    semantic_retention: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Pearson entre matrizes de similaridade coseno antes e depois. "
            "1.0 = estrutura semântica intacta."
        ),
    )
    fit_time_ms: int = Field(ge=0)
    transform_time_ms: int = Field(ge=0)
    n_vectors: int = Field(ge=0)


class BenchmarkCompressionResponse(BaseModel):
    """Resultado completo do benchmark dos 4 compressores.

    `results` vem ordenado por `semantic_retention` decrescente.
    `original_storage_mb` e `best_storage_mb` permitem à banca
    calcular o impacto financeiro em Pinecone/Qdrant diretamente.
    """

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    results: list[CompressorBenchmarkItem]
    best_method: CompressionMethod
    best_semantic_retention: float = Field(ge=0.0, le=1.0)
    original_storage_mb: float = Field(ge=0.0)
    best_storage_mb: float = Field(ge=0.0)
    savings_pct: float = Field(description="Economia percentual do melhor compressor vs original.")
