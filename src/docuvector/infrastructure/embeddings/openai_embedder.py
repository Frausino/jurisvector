"""Embedder usando a API da OpenAI (`text-embedding-3-small`).

O SDK oficial da OpenAI já implementa retry com backoff exponencial
internamente (parâmetro `max_retries`). Não reimplementamos retry
aqui; configuramos o cliente uma vez e confiamos no SDK.
"""

from __future__ import annotations

from collections.abc import Sequence

from openai import OpenAI

from docuvector.domain.enums import EmbeddingProviderName
from docuvector.domain.exceptions import EmbeddingGenerationError
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

# Tamanho máximo de batch suportado pela API de embeddings da OpenAI.
# Acima disso, dividimos em múltiplas chamadas (transparente ao caller).
_MAX_BATCH_SIZE = 100


class OpenAiEmbedder:
    """Implementa `EmbeddingProvider` chamando a API OpenAI.

    Para o modelo `text-embedding-3-small`, OpenAI ignora a distinção
    query vs passage (o modelo é treinado para tratá-las igualmente).
    Mantemos a API uniforme do contrato; ambos os métodos chamam a
    mesma API.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        dimensions: int,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise EmbeddingGenerationError(
                "OPENAI_API_KEY ausente. Defina no .env ou troque o provedor."
            )
        self._client = OpenAI(api_key=api_key, max_retries=max_retries)
        self._model_name = model_name
        self._dimensions = dimensions

    @property
    def provider_name(self) -> EmbeddingProviderName:
        return EmbeddingProviderName.OPENAI

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> EmbeddingVector:
        if not text.strip():
            raise EmbeddingGenerationError("Texto vazio não pode ser vetorizado.")
        vectors = self._call_embeddings_api([text])
        return vectors[0]

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        if not texts:
            return []

        all_vectors: list[EmbeddingVector] = []
        for batch_start in range(0, len(texts), _MAX_BATCH_SIZE):
            current_batch = list(texts[batch_start : batch_start + _MAX_BATCH_SIZE])
            all_vectors.extend(self._call_embeddings_api(current_batch))
        return all_vectors

    def _call_embeddings_api(self, texts: list[str]) -> list[EmbeddingVector]:
        """Faz uma chamada à API de embeddings da OpenAI.

        Erros do SDK viram `EmbeddingGenerationError` (domínio). A
        validação de dimensão protege contra mudanças silenciosas do
        modelo no servidor.
        """
        try:
            response = self._client.embeddings.create(
                model=self._model_name,
                input=texts,
            )
        except Exception as openai_failure:
            raise EmbeddingGenerationError(
                f"Falha ao gerar embeddings via OpenAI: {openai_failure}"
            ) from openai_failure

        vectors: list[EmbeddingVector] = []
        for item in response.data:
            vector_tuple = tuple(item.embedding)
            if len(vector_tuple) != self._dimensions:
                raise EmbeddingGenerationError(
                    f"Dimensão inesperada da OpenAI: esperava {self._dimensions}, "
                    f"recebeu {len(vector_tuple)}. Modelo pode ter mudado."
                )
            vectors.append(vector_tuple)
        return vectors
