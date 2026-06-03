"""Cliente LLM determinístico para CI, dev offline e demos.

Não faz nenhuma chamada de rede. Detecta a presença de contexto
**reusando as constantes públicas** de `application/prompts/legal_prompt.py`,
em vez de duplicar literais. Se o formato do prompt mudar, este cliente
acompanha automaticamente (acoplamento por import, não por string
duplicada).

Comportamento:

- Prompt contém o marcador de contexto presente → resposta canônica
  citando [1], com `[MOCK]` no prefixo para ficar óbvio na demo.
- Prompt contém o marcador de ausência de contexto → frase canônica
  de abstenção (a mesma que o `AnswerUseCase` detecta para marcar
  `grounded=False`).

Métricas fixas: zero tokens, zero custo, latência simbólica de 1 ms,
modelo `"mock"`. Audit log fica explícito sobre origem mockada.
"""

from __future__ import annotations

from docuvector.application.prompts.legal_prompt import (
    ABSTENTION_PHRASE,
    HAS_CONTEXT_MARKER,
    NO_CONTEXT_MARKER,
)
from docuvector.domain.interfaces.llm_client import LlmCompletion

_CANONICAL_ANSWER_WITH_CONTEXT = (
    "[MOCK] Resposta determinística com base no trecho [1]. "
    "Este cliente é usado apenas em CI, desenvolvimento offline ou demos."
)


class MockLlmClient:
    """Implementa `LlmClient` sem chamar nenhum modelo real."""

    def complete(self, system_prompt: str, user_prompt: str) -> LlmCompletion:
        if NO_CONTEXT_MARKER in user_prompt:
            response_text = ABSTENTION_PHRASE
        elif HAS_CONTEXT_MARKER in user_prompt:
            response_text = _CANONICAL_ANSWER_WITH_CONTEXT
        else:
            # Prompt em formato inesperado: por segurança, abstém.
            response_text = ABSTENTION_PHRASE

        return LlmCompletion(
            text=response_text,
            tokens_used=0,
            cost_usd=0.0,
            latency_ms=1,
            model="mock",
        )
