"""Schemas Pydantic para o recurso `queries`."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from docuvector.domain.enums import EmbeddingProviderName

_MIN_QUERY_LENGTH = 3
_MAX_QUERY_LENGTH = 1000


class AskRequest(BaseModel):
    """Pergunta do usuário ao seu corpus.

    `embedding_provider` precisa coincidir com o provider usado no
    upload dos documentos a serem pesquisados; o ChromaDB indexa
    vetores em uma única collection e os vetores têm dimensões
    distintas por provider. Misturar provider de query e de ingestão
    devolve resultados vazios ou erro de dimensão.
    """

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        min_length=_MIN_QUERY_LENGTH,
        max_length=_MAX_QUERY_LENGTH,
        description="Pergunta em texto livre, em português.",
    )
    embedding_provider: EmbeddingProviderName = Field(
        default=EmbeddingProviderName.SENTENCE_TRANSFORMERS,
        description=(
            "Provedor de embedding usado para vetorizar a query. Deve "
            "ser o mesmo usado no upload dos documentos."
        ),
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Sobrescreve RAG_TOP_K se informado.",
    )
    similarity_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Sobrescreve RAG_SIMILARITY_THRESHOLD se informado.",
    )


class SourceCitation(BaseModel):
    """Trecho usado como fonte na resposta, exposto com número de citação."""

    model_config = ConfigDict(frozen=True)

    citation_number: int = Field(ge=1, description="Número usado na resposta: [1], [2]...")
    chunk_id: UUID
    document_id: UUID
    document_filename: str
    text_excerpt: str = Field(
        description="Trecho exato indexado no Chroma (para auditoria/visualização)."
    )
    similarity: float = Field(ge=0.0, le=1.0)
    chunk_index: int = Field(ge=0)


class AnswerResponse(BaseModel):
    """Resposta gerada pelo LLM com fontes e métricas para o dashboard."""

    model_config = ConfigDict(frozen=True)

    query: str
    answer: str
    sources: list[SourceCitation]
    grounded: bool = Field(
        description=(
            "False quando o LLM se absteve por falta de contexto. "
            "Front-end usa para exibir indicador de baixa confiança."
        )
    )
    tokens_used: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    model: str
