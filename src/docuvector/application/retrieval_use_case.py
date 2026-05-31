"""Caso de uso de retrieval semântico sobre os documentos do usuário.

Responsabilidade ÚNICA: dada uma query em texto, devolve a lista de
chunks mais similares pertencentes ao dono autenticado. NÃO chama LLM,
NÃO emite audit (essa orquestração fica no `AnswerUseCase`).

Defesas de contrato:

1.  Query vazia / só whitespace → `ValidationError`. O VectorStore
    abaixo aceitaria, mas o resultado seria lixo (vetor de zeros).
    Falha cedo é melhor que devolver chunks aleatórios.

2.  `owner_id` é parâmetro obrigatório e propagado direto ao Chroma.
    Defesa contra BOLA built-in: nunca há um caminho que busca em
    chunks de outro tenant.

3.  `top_k` e `similarity_threshold` vêm do Settings via injeção no
    construtor. O caller (router) pode sobrescrever no momento da
    chamada se a UI expuser controle (Sprint 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.exceptions import ValidationError
from docuvector.domain.interfaces import EmbeddingProvider, VectorStore

_MIN_QUERY_LENGTH = 3


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Resultado do retrieval. `chunks` já vem ordenado por similaridade desc."""

    query: str
    chunks: tuple[RetrievedChunk, ...]


class RetrievalUseCase:
    """Busca semântica em documentos de um único dono."""

    def __init__(
        self,
        vector_store: VectorStore,
        default_top_k: int,
        default_similarity_threshold: float,
    ) -> None:
        self._vector_store = vector_store
        self._default_top_k = default_top_k
        self._default_similarity_threshold = default_similarity_threshold

    def retrieve(
        self,
        owner_id: UUID,
        query: str,
        embedding_provider: EmbeddingProvider,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> RetrievalResult:
        """Recupera chunks mais similares à query no escopo do dono."""
        normalized_query = self._normalize_and_validate(query)

        effective_top_k = top_k if top_k is not None else self._default_top_k
        effective_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else self._default_similarity_threshold
        )

        query_embedding = embedding_provider.embed_query(normalized_query)
        retrieved_chunks: Sequence[RetrievedChunk] = self._vector_store.search(
            owner_id=owner_id,
            query_embedding=query_embedding,
            top_k=effective_top_k,
            similarity_threshold=effective_threshold,
        )

        return RetrievalResult(
            query=normalized_query,
            chunks=tuple(retrieved_chunks),
        )

    @staticmethod
    def _normalize_and_validate(query: str) -> str:
        """Trim + validação de tamanho mínimo. Falha cedo em queries inúteis."""
        if query is None:
            raise ValidationError("Pergunta é obrigatória.")
        normalized = query.strip()
        if len(normalized) < _MIN_QUERY_LENGTH:
            raise ValidationError(f"Pergunta deve ter pelo menos {_MIN_QUERY_LENGTH} caracteres.")
        return normalized
