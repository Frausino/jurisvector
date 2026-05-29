"""Contrato para geração de embeddings vetoriais."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from docuvector.domain.enums import EmbeddingProviderName

EmbeddingVector = tuple[float, ...]


class EmbeddingProvider(Protocol):
    """Gera embeddings de texto, distinguindo papel de query vs passage.

    A distinção é essencial para modelos como `intfloat/multilingual-e5-*`
    que esperam prefixos `query:` e `passage:` para produzir vetores
    comparáveis. OpenAI ignora a distinção, mas mantemos a API uniforme
    para que o use case nunca precise saber qual provedor está em uso.

    `dimensions` é o contrato com o VectorStore: trocar o modelo exige
    recalcular embeddings ou rejeitar o vetor de dimensão divergente.
    """

    @property
    def provider_name(self) -> EmbeddingProviderName:
        """Nome canônico do provedor (persistido em DocumentChunk)."""
        ...

    @property
    def model_name(self) -> str:
        """Identificador do modelo concreto (ex.: 'text-embedding-3-small')."""
        ...

    @property
    def dimensions(self) -> int:
        """Tamanho do vetor produzido pelo modelo."""
        ...

    def embed_query(self, text: str) -> EmbeddingVector:
        """Vetoriza uma string usada como busca."""
        ...

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        """Vetoriza fragmentos de documento (batch para eficiência)."""
        ...
