"""Cliente LLM usando a API OpenAI Chat Completions.

Modelo padrão: `gpt-4o-mini` (rápido, barato, qualidade adequada para
Q&A com contexto recuperado).

O SDK oficial da OpenAI já implementa retry com backoff exponencial
(`max_retries`); não reimplementamos retry aqui.

Métricas obrigatórias por chamada:
- `tokens_used`  : input + output (do `usage` da resposta)
- `cost_usd`     : calculado pela tabela de preços versionada
- `latency_ms`   : medido entre request e response
- `model`        : echo do modelo usado (reproduzibilidade futura)

Decisão arquitetural: a ausência de `api_key` NÃO falha a construção.
Construir o cliente é parte do wiring de DI; falhar aqui derrubaria
fluxos que nem chegam a chamar o LLM (ex.: validação de input de
query). A falha vira `LlmGenerationError` SOMENTE quando alguém
realmente chama `complete()`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from openai import OpenAI

from docuvector.domain.exceptions import LlmGenerationError
from docuvector.domain.interfaces.llm_client import LlmCompletion
from docuvector.infrastructure.llm.pricing import calculate_cost_usd

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletion


class OpenAiLlmClient:
    """Implementa `LlmClient` chamando a API Chat Completions da OpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 600,
        max_retries: int = 3,
    ) -> None:
        # api_key vazio: cliente fica "armado" mas sem credencial. Qualquer
        # chamada a complete() levanta LlmGenerationError. Permite que a
        # aplicação suba (e que testes que não tocam o LLM passem) mesmo
        # sem OPENAI_API_KEY configurado.
        self._client: OpenAI | None = (
            OpenAI(api_key=api_key, max_retries=max_retries) if api_key else None
        )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LlmCompletion:
        """Executa a inferência e devolve texto + métricas."""
        if self._client is None:
            raise LlmGenerationError("OPENAI_API_KEY ausente. Não é possível gerar respostas.")
        if not user_prompt.strip():
            raise LlmGenerationError("Prompt do usuário está vazio.")

        request_started_at = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as openai_failure:
            raise LlmGenerationError(
                f"Falha na chamada à OpenAI: {openai_failure}"
            ) from openai_failure

        elapsed_milliseconds = int((time.perf_counter() - request_started_at) * 1000)
        return self._build_completion(response, elapsed_milliseconds)

    def _build_completion(
        self,
        openai_response: ChatCompletion,
        elapsed_milliseconds: int,
    ) -> LlmCompletion:
        """Extrai texto e métricas da resposta OpenAI."""
        if not openai_response.choices:
            raise LlmGenerationError("OpenAI devolveu resposta sem 'choices'.")

        first_choice = openai_response.choices[0]
        message_content = first_choice.message.content or ""
        finish_reason = first_choice.finish_reason

        if finish_reason == "content_filter":
            raise LlmGenerationError("Resposta bloqueada pelo filtro de conteúdo.")

        usage = openai_response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        return LlmCompletion(
            text=message_content.strip(),
            tokens_used=total_tokens,
            cost_usd=calculate_cost_usd(self._model, prompt_tokens, completion_tokens),
            latency_ms=elapsed_milliseconds,
            model=self._model,
        )
