"""Endpoints REST de Q&A sobre documentos (`queries`)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from docuvector.api.deps import (
    AnswerUseCaseDependency,
    ClientIpDependency,
    CurrentTokenDependency,
    SettingsDependency,
)
from docuvector.api.limiting import shared_limiter
from docuvector.api.schemas.queries import (
    AnswerResponse,
    AskRequest,
    LlmProviderListResponse,
    LlmProviderOption,
    SourceCitation,
)
from docuvector.application.answer_use_case import AskInput
from docuvector.config.settings import get_settings
from docuvector.domain.entities import Answer
from docuvector.domain.enums import LlmProviderName
from docuvector.infrastructure.embeddings.factory import resolve_embedder
from docuvector.infrastructure.llm.factory import (
    list_available_providers,
    resolve_llm_client,
)

_settings = get_settings()
# Reusa o limit de login (mesmo teto faz sentido para LLM, que é caro).
# Polish futuro: variável dedicada QUERY_RATE_LIMIT_PER_MINUTE.
_QUERY_RATE = f"{_settings.login_rate_limit_per_minute}/minute"


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
        "\n\nO usuário escolhe `embedding_provider` (vetorização) e "
        "`llm_provider` (geração) independentemente. Combinações típicas:\n"
        "- Local: `sentence_transformers` + `ollama`\n"
        "- Cloud: `sentence_transformers` + `openai`\n"
        "- CI/dev offline: qualquer embedding + `mock`"
    ),
    responses={
        200: {"description": "Resposta gerada com sucesso."},
        401: {"description": "Token ausente ou inválido."},
        422: {"description": "Pergunta inválida (vazia ou muito curta)."},
        429: {"description": "Limite de tentativas excedido."},
        502: {"description": "Falha ao chamar o LLM upstream."},
    },
)
@shared_limiter.limit(_QUERY_RATE)
def ask(
    request: Request,
    payload: AskRequest,
    token_payload: CurrentTokenDependency,
    client_ip: ClientIpDependency,
    answer_use_case: AnswerUseCaseDependency,
    settings: SettingsDependency,
) -> AnswerResponse:
    embedder = resolve_embedder(payload.embedding_provider)

    # Resolve LLM por request, NÃO por singleton global. Quando o
    # cliente omite `llm_provider`, aplica o default do Settings.
    effective_llm_provider = payload.llm_provider or settings.llm_default_provider
    llm_client = resolve_llm_client(effective_llm_provider)

    answer = answer_use_case.ask(
        AskInput(
            owner_id=token_payload.user_id,
            query=payload.query,
            embedding_provider=embedder,
            llm_provider=effective_llm_provider,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
            correlation_id=None,
            top_k=payload.top_k,
            similarity_threshold=payload.similarity_threshold,
        ),
        llm_client=llm_client,
    )

    return _serialize_answer(answer, effective_llm_provider)


# =============================================================
# GET /api/v1/queries/llm-providers
# =============================================================
@router.get(
    "/llm-providers",
    response_model=LlmProviderListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar provedores de LLM disponíveis",
    description=(
        "Lista os provedores de LLM disponíveis no ambiente atual. A "
        "UX usa essa listagem para popular o select de escolha. `OPENAI` "
        "só aparece se `OPENAI_API_KEY` estiver configurada."
    ),
)
def list_llm_providers(
    _token_payload: CurrentTokenDependency,
    settings: SettingsDependency,
) -> LlmProviderListResponse:
    available = list_available_providers(settings)

    items: list[LlmProviderOption] = []
    for provider_name in available:
        items.append(_describe_provider(provider_name, settings))

    return LlmProviderListResponse(
        items=items,
        default=settings.llm_default_provider,
    )


# =============================================================
# Helpers
# =============================================================
def _serialize_answer(
    answer: Answer,
    llm_provider: LlmProviderName,
) -> AnswerResponse:
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
        llm_provider=llm_provider,
    )


def _describe_provider(
    provider_name: LlmProviderName,
    settings: SettingsDependency,
) -> LlmProviderOption:
    """Metadados de UX para cada provider."""
    if provider_name is LlmProviderName.OPENAI:
        return LlmProviderOption(
            name=provider_name,
            model=settings.openai_llm_model,
            description="Cloud, alta qualidade, latência baixa. Custo por token.",
            cost_tier="pay-per-token",
        )

    if provider_name is LlmProviderName.OLLAMA:
        return LlmProviderOption(
            name=provider_name,
            model=settings.ollama_model,
            description=(
                "Local via servidor Ollama. Sem custo monetário, sem envio "
                "de dados para fora. Requer ollama em execução."
            ),
            cost_tier="local-zero-cost",
        )

    return LlmProviderOption(
        name=provider_name,
        model="mock",
        description="Determinístico, sem rede. Apenas para CI, dev e demos.",
        cost_tier="free",
    )
