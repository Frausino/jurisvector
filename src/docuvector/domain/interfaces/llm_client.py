"""Contrato para chamadas a um modelo de linguagem (LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LlmCompletion:
    """Resposta de um LLM com metadados para audit e billing.

    Sempre devolve `tokens_used` e `cost_usd` (mesmo que zero, em modos
    offline). O use case de answer propaga isso para o audit log.
    """

    text: str
    tokens_used: int
    cost_usd: float
    latency_ms: int
    model: str


class LlmClient(Protocol):
    """Chama um LLM para gerar texto a partir de um prompt.

    A construção do prompt (system + context + query) é responsabilidade
    do use case, não do cliente. O cliente concreto só sabe falar com
    a API do provedor.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> LlmCompletion:
        """Executa a inferência e devolve texto + métricas."""
        ...
