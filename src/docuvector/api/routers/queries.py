"""Endpoints REST de Q&A sobre documentos (`queries`)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from docuvector.api.deps import (
    AnswerUseCaseDependency,
    ClientIpDependency,
    CurrentTokenDependency,
)
from docuvector.api.schemas.queries import (
    AnswerResponse,
    AskRequest,
    SourceCitation,
)
from docuvector.application.answer_use_case import AskInput
from docuvector.config.settings import get_settings
from docuvector.domain.entities import Answer
from docuvector.infrastructure.embeddings.factory import resolve_embedder

_settings = get_settings()
# Reusa o limit de login (10/min default). LLM é caro; faz sentido o
# mesmo teto. Em Sprint futura, expor QUERY_RATE_LIMIT_PER_MINUTE como
# variável dedicada no Settings.
_QUERY_RATE = f"{_settings.login_rate_limit_per_minute}/minute"

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1/queries", tags=["queries"])


# =============================================================
# POST /api/v1/queries/ask
# =============================================================
@router.post(
    "/ask",
    response_model=AnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Perguntar ao corpus do usuário autenticado",
    description=(
        "Recupera os trechos mais similares à pergunta dentro dos "
        "documentos do usuário, monta um prompt jurídico com citações "
        "numeradas e devolve a resposta do LLM com as fontes utilizadas. "
        "\n\nO provedor de embedding informado precisa ser o mesmo usado "
        "no upload dos documentos a serem pesquisados."
    ),
    responses={
        200: {"description": "Resposta gerada com sucesso."},
        401: {"description": "Token ausente ou inválido."},
        422: {"description": "Pergunta inválida (vazia ou muito curta)."},
        429: {"description": "Limite de tentativas excedido."},
        502: {"description": "Falha ao chamar o LLM upstream."},
    },
)
@limiter.limit(_QUERY_RATE)
def ask(
    request: Request,
    payload: AskRequest,
    token_payload: CurrentTokenDependency,
    client_ip: ClientIpDependency,
    answer_use_case: AnswerUseCaseDependency,
) -> AnswerResponse:
    embedder = resolve_embedder(payload.embedding_provider)

    answer = answer_use_case.ask(
        AskInput(
            owner_id=token_payload.user_id,
            query=payload.query,
            embedding_provider=embedder,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
            correlation_id=None,
            top_k=payload.top_k,
            similarity_threshold=payload.similarity_threshold,
        ),
    )

    return _serialize_answer(answer)


def _serialize_answer(answer: Answer) -> AnswerResponse:
    """Converte a entidade `Answer` no schema HTTP com citações numeradas."""
    citations: list[SourceCitation] = []
    for citation_number, source_chunk in enumerate(answer.sources, start=1):
        citations.append(
            SourceCitation(
                citation_number=citation_number,
                chunk_id=source_chunk.chunk_id,
                document_id=source_chunk.document_id,
                document_filename=source_chunk.document_filename,
                text_excerpt=source_chunk.text,
                similarity=source_chunk.similarity,
                chunk_index=source_chunk.chunk_index,
            ),
        )

    return AnswerResponse(
        query=answer.query,
        answer=answer.text,
        sources=citations,
        grounded=answer.grounded,
        tokens_used=answer.tokens_used,
        cost_usd=answer.cost_usd,
        latency_ms=answer.latency_ms,
        model=answer.model,
    )
