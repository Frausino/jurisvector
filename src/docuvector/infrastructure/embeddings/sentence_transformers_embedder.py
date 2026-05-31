"""Embedder local usando `sentence-transformers` (modelo multilingual E5).

Decisão arquitetural CRÍTICA: o modelo E5 exige prefixos diferentes
para queries e passages, conforme paper original (Wang et al. 2024):
- `embed_query` adiciona `"query: "` antes do texto.
- `embed_passages` adiciona `"passage: "` antes de cada texto.

Sem esses prefixos, os vetores resultantes não são comparáveis e o
sistema de retrieval degrada severamente. Por isso a interface
`EmbeddingProvider` força a distinção desde o domínio.

O modelo é carregado preguiçosamente na primeira chamada (cold start
~3-5s, primeira execução baixa ~118MB para `HF_HOME`). Instância é
mantida em memória pelo factory singleton no `composition root`.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
from typing import TYPE_CHECKING

from docuvector.domain.enums import EmbeddingProviderName
from docuvector.domain.exceptions import EmbeddingGenerationError
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "
_DEFAULT_BATCH_SIZE = 32


class SentenceTransformersEmbedder:
    """Implementa `EmbeddingProvider` com `intfloat/multilingual-e5-small`.

    Vetores produzidos são L2-normalizados (`normalize_embeddings=True`),
    necessário porque a similaridade no ChromaDB é distância coseno e o
    Sprint 4 (compressão) assume vetores unitários.
    """

    def __init__(
        self,
        model_name: str,
        dimensions: int,
        cache_folder: str | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._cache_folder = cache_folder
        self._batch_size = batch_size
        self._model: SentenceTransformer | None = None

    @property
    def provider_name(self) -> EmbeddingProviderName:
        return EmbeddingProviderName.SENTENCE_TRANSFORMERS

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> EmbeddingVector:
        if not text.strip():
            raise EmbeddingGenerationError("Texto vazio não pode ser vetorizado.")
        return self._encode_single(_QUERY_PREFIX + text)

    def embed_passages(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        if not texts:
            return []
        prefixed_texts = [_PASSAGE_PREFIX + text for text in texts]
        return self._encode_batch(prefixed_texts)

    def _ensure_model_loaded(self) -> SentenceTransformer:
        """Carrega o modelo na primeira chamada e reaproveita depois."""
        if self._model is None:
            try:
                sentence_transformers_module = import_module("sentence_transformers")
                sentence_transformer_class = sentence_transformers_module.SentenceTransformer
            except ImportError as missing_dependency:
                raise EmbeddingGenerationError(
                    "sentence-transformers não está instalado."
                ) from missing_dependency

            self._model = sentence_transformer_class(
                self._model_name,
                cache_folder=self._cache_folder,
            )

        return self._model

    def _encode_single(self, text: str) -> EmbeddingVector:
        model = self._ensure_model_loaded()
        try:
            vector_array = model.encode(
                text,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as encoding_failure:
            raise EmbeddingGenerationError(
                f"Falha ao gerar embedding local: {encoding_failure}"
            ) from encoding_failure

        vector_tuple: EmbeddingVector = tuple(float(component) for component in vector_array)
        self._assert_expected_dimensions(vector_tuple)
        return vector_tuple

    def _encode_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        model = self._ensure_model_loaded()
        try:
            vector_arrays = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self._batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as encoding_failure:
            raise EmbeddingGenerationError(
                f"Falha ao gerar embeddings locais em batch: {encoding_failure}"
            ) from encoding_failure

        vectors: list[EmbeddingVector] = []
        for vector_array in vector_arrays:
            vector_tuple: EmbeddingVector = tuple(float(component) for component in vector_array)
            self._assert_expected_dimensions(vector_tuple)
            vectors.append(vector_tuple)
        return vectors

    def _assert_expected_dimensions(self, vector: EmbeddingVector) -> None:
        """Garante que o modelo retornou vetor com a dimensão prometida."""
        if len(vector) != self._dimensions:
            raise EmbeddingGenerationError(
                f"Dimensão inesperada: esperava {self._dimensions}, "
                f"recebeu {len(vector)} para o modelo {self._model_name}."
            )
