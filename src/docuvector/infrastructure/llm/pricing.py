"""Tabela de preços por modelo OpenAI.

Fonte: https://openai.com/api/pricing/ (consultado em 05/2026).
Valores em USD por 1 milhão de tokens. Atualizações futuras alteram
apenas este arquivo; nenhum LLM client tem preços hardcoded.

Decisão: NÃO usar API de preços dinâmica. Preços mudam raramente; a
tabela versionada no repositório é auditável e reproduz custos
históricos exatos quando se consulta um audit_log antigo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Preço por 1 milhão de tokens, em USD."""

    input_usd_per_million: float
    output_usd_per_million: float


_OPENAI_PRICING_TABLE: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(
        input_usd_per_million=0.15,
        output_usd_per_million=0.60,
    ),
    "gpt-4o": ModelPricing(
        input_usd_per_million=2.50,
        output_usd_per_million=10.00,
    ),
}


def calculate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calcula o custo total em USD da chamada.

    Modelo desconhecido devolve 0.0 (não levanta exceção). Audit log
    fica com custo zero, sinalizando que o modelo precisa ser
    cadastrado na tabela, sem quebrar o pipeline em produção.
    """
    pricing = _OPENAI_PRICING_TABLE.get(model)
    if pricing is None:
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * pricing.input_usd_per_million
    output_cost = (completion_tokens / 1_000_000) * pricing.output_usd_per_million
    return round(input_cost + output_cost, 6)
