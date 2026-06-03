"""Caso de uso de geração de resposta com fontes (orquestrador RAG).

Composição:

    RetrievalUseCase  →  build_user_prompt  →  LlmClient.complete
                                                       ↓
                                            AuditRepository.append
                                                       ↓
                                                    Answer

Pontos de design:

1.  **LLM é parâmetro do método `ask`, não do `__init__`.** O router
    resolve qual provider usar a partir do `llm_provider` na request
    e passa explicitamente para o use case. Isso permite alternar
    OpenAI/Ollama/Mock por chamada, sem singleton fixo e sem fallback
    escondido. O use case fica stateless quanto ao vendor.

2.  **Audit centralizado aqui, não no retrieval.** Uma pergunta = um
    evento `QUERY_EXECUTED`. O `metadata` carrega o `llm_provider` usado,
    permitindo dashboards de custo/latência por provider sem schema
    adicional.

3.  **`grounded` detectado pelo texto canônico.** O prompt instrui o
    LLM a usar uma frase EXATA quando não tem contexto suficiente.
    Detectamos essa frase para marcar a resposta como não-fundamentada
    e o front exibe um indicador. Heurística robusta a pequenas
    variações via `casefold`.

4.  **Sem retry no nível do use case.** Cada cliente concreto decide
    sua política (SDK da OpenAI tem retry; Ollama, não). Re-tentar
    aqui mascararia o vendor e geraria custo dobrado em cloud.

5.  **`correlation_id` propagado para o audit.** Hoje é None, mas a
    entidade já suporta. Quando o middleware de tracing entrar, todos
    os eventos da mesma requisição ficam encadeados sem mudar este
    código.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

from docuvector.application.prompts import build_user_prompt, get_system_prompt
from docuvector.application.retrieval_use_case import RetrievalUseCase
from docuvector.domain.entities import Answer, AuditEvent
from docuvector.domain.enums import AuditAction, AuditStatus, LlmProviderName
from docuvector.domain.exceptions import LlmGenerationError
from docuvector.domain.interfaces import AuditRepository, EmbeddingProvider, LlmClient

_RESOURCE_TYPE = "query"
_NOT_ENOUGH_CONTEXT_FRAGMENT = "não tenho contexto suficiente"


@dataclass(frozen=True, slots=True)
class AskInput:
    """Entrada compacta para o caso de uso.

    `llm_provider` é metadado de auditoria: identifica qual provider
    o router resolveu. O `LlmClient` correspondente já foi instanciado
    e é passado separadamente para `ask`.
    """

    owner_id: UUID
    query: str
    embedding_provider: EmbeddingProvider
    llm_provider: LlmProviderName
    client_ip: str | None = None
    user_agent: str | None = None
    correlation_id: UUID | None = None
    top_k: int | None = None
    similarity_threshold: float | None = None


class AnswerUseCase:
    """Orquestra retrieval + LLM + audit em torno de uma pergunta."""

    def __init__(
        self,
        retrieval_use_case: RetrievalUseCase,
        audit_repository: AuditRepository,
    ) -> None:
        self._retrieval = retrieval_use_case
        self._audit = audit_repository

    def ask(self, ask_input: AskInput, llm_client: LlmClient) -> Answer:
        """Executa pergunta → contexto → resposta com fontes.

        `llm_client` é OBRIGATÓRIO e vem do router (resolvido pelo
        `llm_provider` da request). Sem fallback escondido: se o
        router não passar, o tipo já falha.
        """
        wall_clock_start = time.perf_counter()

        retrieval_result = self._retrieval.retrieve(
            owner_id=ask_input.owner_id,
            query=ask_input.query,
            embedding_provider=ask_input.embedding_provider,
            top_k=ask_input.top_k,
            similarity_threshold=ask_input.similarity_threshold,
        )

        try:
            completion = llm_client.complete(
                system_prompt=get_system_prompt(),
                user_prompt=build_user_prompt(
                    query=retrieval_result.query,
                    retrieved_chunks=retrieval_result.chunks,
                ),
            )
        except LlmGenerationError:
            self._audit_failure(
                ask_input=ask_input,
                chunks_count=len(retrieval_result.chunks),
                elapsed_ms=int((time.perf_counter() - wall_clock_start) * 1000),
            )
            raise

        total_elapsed_ms = int((time.perf_counter() - wall_clock_start) * 1000)
        is_grounded = self._is_answer_grounded(
            completion_text=completion.text,
            had_context=bool(retrieval_result.chunks),
        )

        answer = Answer(
            query=retrieval_result.query,
            text=completion.text,
            sources=retrieval_result.chunks,
            tokens_used=completion.tokens_used,
            cost_usd=completion.cost_usd,
            latency_ms=total_elapsed_ms,
            model=completion.model,
            grounded=is_grounded,
        )

        self._audit_success(ask_input=ask_input, answer=answer)
        return answer

    # -------------------------------------------------------------
    # Helpers privados
    # -------------------------------------------------------------
    @staticmethod
    def _is_answer_grounded(completion_text: str, had_context: bool) -> bool:
        """Resposta é fundamentada quando o LLM teve contexto E não abstém."""
        if not had_context:
            return False
        normalized_text = completion_text.casefold()
        return _NOT_ENOUGH_CONTEXT_FRAGMENT not in normalized_text

    def _audit_success(self, ask_input: AskInput, answer: Answer) -> None:
        self._audit.append(
            AuditEvent(
                actor_user_id=ask_input.owner_id,
                action=AuditAction.QUERY_EXECUTED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=None,
                ip_address=ask_input.client_ip,
                user_agent=ask_input.user_agent,
                correlation_id=ask_input.correlation_id,
                metadata={
                    "query_length": len(answer.query),
                    "sources_count": len(answer.sources),
                    "tokens_used": answer.tokens_used,
                    "cost_usd": answer.cost_usd,
                    "latency_ms": answer.latency_ms,
                    "model": answer.model,
                    "grounded": answer.grounded,
                    "embedding_provider": ask_input.embedding_provider.provider_name.value,
                    "llm_provider": ask_input.llm_provider.value,
                },
            )
        )

    def _audit_failure(
        self,
        ask_input: AskInput,
        chunks_count: int,
        elapsed_ms: int,
    ) -> None:
        self._audit.append(
            AuditEvent(
                actor_user_id=ask_input.owner_id,
                action=AuditAction.QUERY_EXECUTED,
                status=AuditStatus.FAILURE,
                resource_type=_RESOURCE_TYPE,
                resource_id=None,
                ip_address=ask_input.client_ip,
                user_agent=ask_input.user_agent,
                correlation_id=ask_input.correlation_id,
                metadata={
                    "sources_count": chunks_count,
                    "latency_ms": elapsed_ms,
                    "embedding_provider": ask_input.embedding_provider.provider_name.value,
                    "llm_provider": ask_input.llm_provider.value,
                    "reason": "llm_failure",
                },
            )
        )
