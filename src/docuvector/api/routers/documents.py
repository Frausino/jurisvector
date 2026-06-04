"""Endpoints REST do recurso `documents`."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from docuvector.api.deps import (
    ClientIpDependency,
    CompressionBenchmarkUseCaseDependency,
    CurrentTokenDependency,
    DocumentCrudUseCaseDependency,
    IngestionUseCaseDependency,
    SettingsDependency,
)
from docuvector.api.schemas.benchmark import (
    BenchmarkCompressionRequest,
    BenchmarkCompressionResponse,
    CompressorBenchmarkItem,
)
from docuvector.api.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    EmbeddingProviderListResponse,
    EmbeddingProviderOption,
)
from docuvector.application.compression_benchmark_use_case import BenchmarkInput
from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.enums import EmbeddingProviderName
from docuvector.domain.exceptions import DocumentTooLargeError
from docuvector.infrastructure.embeddings.factory import (
    list_available_providers,
    resolve_embedder,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Lê o upload em pedaços de 1 MB. Equilibra throughput (poucas system
# calls) com memória (pico controlado mesmo em paralelo).
_UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024


# =============================================================
# POST /api/v1/documents (upload + ingestão completa)
# =============================================================
@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload e ingestão de documento",
    description=(
        "Upload multipart com pipeline completo: extract → split → embed → store. "
        "O usuário escolhe o `embedding_provider`. Documento duplicado (mesmo "
        "SHA-256 do dono) é detectado e retornado sem reprocessar.\n\n"
        "O corpo é lido em chunks de 1 MB; uploads que excedem o limite "
        "configurado são abortados ANTES de bufferizar tudo na memória."
    ),
    responses={
        201: {"description": "Documento ingerido com sucesso."},
        400: {"description": "Arquivo inválido ou formato não suportado."},
        413: {"description": "Arquivo excede o tamanho máximo."},
        422: {"description": "Provedor de embedding inválido."},
    },
)
async def upload_document(
    request: Request,
    token_payload: CurrentTokenDependency,
    client_ip: ClientIpDependency,
    ingestion_use_case: IngestionUseCaseDependency,
    settings: SettingsDependency,
    file: UploadFile = File(..., description="Arquivo PDF, TXT ou MD."),
    embedding_provider: EmbeddingProviderName = Form(
        default=EmbeddingProviderName.SENTENCE_TRANSFORMERS,
        description="Provedor de embeddings escolhido pelo usuário.",
    ),
) -> DocumentUploadResponse:
    content = await _read_upload_with_size_limit(
        upload_file=file,
        size_limit_bytes=settings.upload_max_bytes,
    )

    embedder = resolve_embedder(embedding_provider)
    ingestion_result = ingestion_use_case.ingest(
        owner_id=token_payload.user_id,
        filename=file.filename or "documento",
        content=content,
        embedding_provider=embedder,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )

    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(ingestion_result.document),
        chunks_created=ingestion_result.chunks_created,
        embedding_provider=ingestion_result.embedding_provider,
        was_already_ingested=ingestion_result.was_already_ingested,
    )


async def _read_upload_with_size_limit(
    upload_file: UploadFile,
    size_limit_bytes: int,
) -> bytes:
    """Lê o `UploadFile` em chunks abortando em quanto exceder o limite.

    Defesa contra OOM: um cliente malicioso pode enviar gigabytes; se
    lermos `await file.read()` direto, alocamos tudo na heap antes de
    checar o tamanho. Aqui acumulamos em chunks e fechamos cedo se
    detectarmos excesso.
    """
    accumulated_bytes = bytearray()
    while True:
        chunk = await upload_file.read(_UPLOAD_CHUNK_SIZE_BYTES)
        if not chunk:
            break

        accumulated_bytes.extend(chunk)
        if len(accumulated_bytes) > size_limit_bytes:
            await upload_file.close()
            raise DocumentTooLargeError(f"Arquivo excede o limite de {size_limit_bytes} bytes.")
    return bytes(accumulated_bytes)


# =============================================================
# GET /api/v1/documents/providers (lista para UX)
# =============================================================
@router.get(
    "/providers",
    response_model=EmbeddingProviderListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar provedores de embedding disponíveis",
)
def list_embedding_providers(
    _token_payload: CurrentTokenDependency,
    settings: SettingsDependency,
) -> EmbeddingProviderListResponse:
    available = list_available_providers(settings)

    items: list[EmbeddingProviderOption] = []
    for provider_name in available:
        if provider_name is EmbeddingProviderName.SENTENCE_TRANSFORMERS:
            items.append(
                EmbeddingProviderOption(
                    name=provider_name,
                    model=settings.sentence_transformers_model,
                    dimensions=settings.sentence_transformers_dimensions,
                    description="Local, multilíngue, sem custo por chamada.",
                )
            )
        elif provider_name is EmbeddingProviderName.OPENAI:
            items.append(
                EmbeddingProviderOption(
                    name=provider_name,
                    model=settings.openai_embedding_model,
                    dimensions=settings.openai_embedding_dimensions,
                    description="Qualidade superior; consome cota da OpenAI.",
                )
            )

    return EmbeddingProviderListResponse(
        items=items,
        default=EmbeddingProviderName.SENTENCE_TRANSFORMERS,
    )


# =============================================================
# GET /api/v1/documents
# =============================================================
@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar documentos do usuário autenticado",
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


# =============================================================
# GET /api/v1/documents/{id}
# =============================================================
@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalhar documento do usuário autenticado",
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


# =============================================================
# POST /api/v1/documents/{id}/benchmark-compression
# =============================================================
@router.post(
    "/{document_id}/benchmark-compression",
    response_model=BenchmarkCompressionResponse,
    status_code=status.HTTP_200_OK,
    summary="Benchmark de compressão de embeddings",
    description=(
        "Executa PCA, RandomProjection, Int8 e Binary sobre os embeddings "
        "reais do documento. Calcula retenção semântica via Pearson de "
        "matrizes de similaridade coseno, persiste o melhor resultado e "
        "retorna a comparação completa.\n\n"
        "`savings_pct` indica a economia de armazenamento do melhor "
        "compressor vs o corpus original em float32."
    ),
    responses={
        200: {"description": "Benchmark executado com sucesso."},
        401: {"description": "Token ausente ou inválido."},
        404: {"description": "Documento não encontrado."},
        422: {"description": "target_dim inválido (mínimo: 2)."},
        502: {"description": "Falha ao acessar vetores no ChromaDB."},
    },
)
def benchmark_compression(
    document_id: UUID,
    payload: BenchmarkCompressionRequest,
    token_payload: CurrentTokenDependency,
    benchmark_use_case: CompressionBenchmarkUseCaseDependency,
) -> BenchmarkCompressionResponse:
    results = benchmark_use_case.run(
        BenchmarkInput(
            owner_id=token_payload.user_id,
            document_id=document_id,
            target_dim=payload.target_dim,
        )
    )

    best = max(results, key=lambda m: m.semantic_retention)

    return BenchmarkCompressionResponse(
        document_id=document_id,
        results=[_to_benchmark_item(m) for m in results],
        best_method=best.method,
        best_semantic_retention=best.semantic_retention,
        original_storage_mb=_bytes_to_mb(best.original_storage_bytes(best.n_vectors)),
        best_storage_mb=_bytes_to_mb(best.storage_bytes(best.n_vectors)),
        savings_pct=round(best.space_savings_pct, 2),
    )


def _to_benchmark_item(metrics: CompressionMetrics) -> CompressorBenchmarkItem:
    """Converte entidade de domínio para o schema HTTP."""
    return CompressorBenchmarkItem(
        method=metrics.method,
        original_dim=metrics.original_dim,
        compressed_dim=metrics.compressed_dim,
        ratio_bytes=metrics.ratio_bytes,
        space_savings_pct=metrics.space_savings_pct,
        semantic_retention=metrics.semantic_retention,
        fit_time_ms=metrics.fit_time_ms,
        transform_time_ms=metrics.transform_time_ms,
        n_vectors=metrics.n_vectors,
    )


def _bytes_to_mb(n_bytes: int) -> float:
    """Converte bytes para megabytes com 4 casas decimais."""
    return round(n_bytes / (1024.0 * 1024.0), 4)


# =============================================================
# DELETE /api/v1/documents/{id}
# =============================================================
@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir documento do usuário autenticado",
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
