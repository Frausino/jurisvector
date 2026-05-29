"""Tipos de retorno do pipeline de retrieval e answer.

Não são entidades persistidas; são DTOs imutáveis que transitam entre
use cases e o router. Mantidos no domínio porque o router fala sobre
eles e a camada de aplicação os constrói.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Chunk recuperado por similaridade semântica, pronto para citação.

    `similarity` é o score de similaridade normalizado em [0, 1] devolvido
    pelo VectorStore. O use case de retrieval aplica um threshold antes
    de devolver para evitar contexto irrelevante chegar ao LLM.
    """

    chunk_id: UUID
    document_id: UUID
    document_filename: str
    text: str
    similarity: float
    chunk_index: int


@dataclass(frozen=True, slots=True)
class Answer:
    """Resposta gerada pelo LLM com rastreabilidade completa.

    `sources` é obrigatório (mesmo que vazio): garante que qualquer
    resposta possa ser auditada. `cost_usd` e `tokens_used` alimentam
    o audit log e o dashboard de custo da Sprint 4.
    """

    query: str
    text: str
    sources: tuple[RetrievedChunk, ...]
    tokens_used: int
    cost_usd: float
    latency_ms: int
    model: str
    grounded: bool = field(default=True)
