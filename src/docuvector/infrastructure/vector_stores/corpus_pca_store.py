"""VectorStore com PCA treinado no corpus completo do owner.

Correções em relação à versão anterior (review P0):

P0 — Search sem efeito colateral:
    `search()` não deve treinar o PCA. Efeito colateral em read-only
    viola o princípio de menor surpresa e torna o comportamento
    não-determinístico para o chamador.
    Solução: `fit_corpus()` é método público explícito, chamado pelo
    `IngestionUseCase` após indexar todos os chunks de um batch.

P0 — Sem duplicação de índice:
    `_reindex_pending()` limpava o índice ChromaDB interno antes de
    re-adicionar. Sem a limpeza, re-treinamento gerava duplicação.
    Solução: `delete_document()` no inner store antes de `add_chunks()`.

P1 — Reprodutibilidade (explainability):
    `explained_variance_ratio_` do PCA registrado no `pca_metadata`.
    Responde à pergunta da banca: "quanto da variância foi preservada?"

Limitações documentadas (escopo TCC):
    - PCA não é serializado em disco. Reiniciar a aplicação requer
      nova chamada a `fit_corpus()`. Serialização via joblib é próxima
      evolução.
    - `fit_corpus()` trava a primeira ingestão em corpora grandes
      (cold start). Em produção seria assíncrono com filas.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sklearn.decomposition import PCA

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces import ChunkVector, VectorStore
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

logger = logging.getLogger(__name__)

_MIN_SAMPLES_FOR_FIT = 2


@dataclass(frozen=True, slots=True)
class PcaModelMetadata:
    """Metadados do modelo PCA treinado — rastreabilidade e reprodutibilidade."""

    n_samples: int
    original_dim: int
    target_dim: int
    explained_variance_ratio: float  # soma dos ratios dos componentes
    model_hash: str  # SHA-256 dos componentes principais


class CorpusPcaStore:
    """PCA global treinado no corpus completo, não por documento.

    Fluxo correto de uso:
        store = CorpusPcaStore(inner_store, target_dim=192)
        store.add_chunks(chunks_doc_a)     # bufferiza sem indexar
        store.add_chunks(chunks_doc_b)     # bufferiza sem indexar
        store.fit_corpus()                 # treina PCA global e indexa
        results = store.search(...)        # lê do índice PCA global
    """

    def __init__(
        self,
        inner_store: VectorStore,
        target_dim: int,
    ) -> None:
        self._inner: VectorStore = inner_store
        self._target_dim = target_dim
        self._pca: PCA | None = None
        self._model_metadata: PcaModelMetadata | None = None
        # Buffer: (chunk, vetor_original) até fit_corpus() ser chamado.
        self._pending: list[tuple[ChunkVector, NDArray[np.float32]]] = []

    # ------------------------------------------------------------------
    # Interface VectorStore (protocolo)
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        """Bufferiza os chunks sem indexar.

        O índice PCA só é construído após `fit_corpus()`.
        Invalidar o PCA quando novos dados chegam é correto: o espaço
        global muda com cada novo documento.
        """
        if not chunks:
            return
        for chunk in chunks:
            vector = np.array(list(chunk.embedding), dtype=np.float32)
            self._pending.append((chunk, vector))
        # Invalida o modelo: novos dados exigem re-treinamento.
        self._pca = None
        self._model_metadata = None

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Busca no índice PCA global.

        Sem efeito colateral: não treina nem indexa nada.
        Se `fit_corpus()` ainda não foi chamado, retorna lista vazia
        e registra aviso em log.
        """
        if self._pca is None:
            logger.warning(
                "CorpusPcaStore.search chamado sem PCA treinado. "
                "Chame fit_corpus() após adicionar os documentos."
            )
            return []

        compressed_query = self._project(
            np.array(list(query_embedding), dtype=np.float32).reshape(1, -1)
        )[0]
        return self._inner.search(
            owner_id=owner_id,
            query_embedding=tuple(float(v) for v in compressed_query),
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        """Retorna vetores PCA persistidos (não os originais)."""
        return self._inner.get_vectors_for_document(owner_id, document_id)

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        """Remove do buffer e do índice. Invalida o PCA."""
        self._pending = [
            (chunk, vec) for chunk, vec in self._pending if chunk.document_id != document_id
        ]
        self._pca = None
        self._model_metadata = None
        return self._inner.delete_document(owner_id, document_id)

    # ------------------------------------------------------------------
    # API pública de treinamento
    # ------------------------------------------------------------------

    def fit_corpus(self) -> PcaModelMetadata:
        """Treina o PCA global e indexa todos os chunks pendentes.

        Deve ser chamado explicitamente após `add_chunks()`.
        Limpa o índice existente antes de re-indexar para evitar
        duplicação de vetores.

        Returns:
            PcaModelMetadata com hash e explained_variance_ratio.

        Raises:
            VectorStoreError: se o fit falhar.
        """
        if not self._pending:
            raise VectorStoreError(
                "fit_corpus() chamado sem chunks no buffer. Use add_chunks() antes de treinar."
            )

        all_vectors = np.vstack([vec for _, vec in self._pending])
        n_samples, n_dims = all_vectors.shape

        effective_target = min(self._target_dim, n_samples - 1, n_dims)
        if effective_target < 1:
            raise VectorStoreError(
                f"Corpus insuficiente para PCA: n_samples={n_samples}, "
                f"n_dims={n_dims}, target_dim={self._target_dim}."
            )

        try:
            pca = PCA(n_components=effective_target, svd_solver="full")
            pca.fit(all_vectors)
        except Exception as fit_failure:
            raise VectorStoreError(f"Falha ao treinar PCA global: {fit_failure}") from fit_failure

        self._pca = pca
        self._model_metadata = PcaModelMetadata(
            n_samples=n_samples,
            original_dim=n_dims,
            target_dim=effective_target,
            explained_variance_ratio=float(np.sum(pca.explained_variance_ratio_)),
            model_hash=self._hash_pca(pca),
        )

        logger.info(
            "PCA global treinado.",
            extra={
                "n_samples": n_samples,
                "target_dim": effective_target,
                "explained_variance": self._model_metadata.explained_variance_ratio,
                "model_hash": self._model_metadata.model_hash[:12],
            },
        )

        self._reindex_all(all_vectors)
        return self._model_metadata

    @property
    def model_metadata(self) -> PcaModelMetadata | None:
        """Metadados do PCA treinado, ou None se ainda não treinado."""
        return self._model_metadata

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _project(self, matrix: NDArray[np.float32]) -> NDArray[np.float32]:
        assert self._pca is not None
        result: NDArray[np.float32] = np.asarray(self._pca.transform(matrix), dtype=np.float32)
        return result

    def _reindex_all(self, all_vectors: NDArray[np.float32]) -> None:
        """Limpa o índice existente e re-indexa no espaço PCA global.

        A limpeza por documento (via delete_document) antes de add_chunks
        evita duplicação de IDs quando fit_corpus() é chamado múltiplas vezes.
        """
        assert self._pca is not None
        compressed = self._project(all_vectors)

        # Agrupa por document_id para limpar antes de re-inserir.
        doc_ids_seen: set[UUID] = set()
        for chunk, _ in self._pending:
            if chunk.document_id not in doc_ids_seen:
                self._inner.delete_document(chunk.owner_id, chunk.document_id)
                doc_ids_seen.add(chunk.document_id)

        compressed_chunks = [
            ChunkVector(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                owner_id=chunk.owner_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding=tuple(float(v) for v in compressed[i]),
                document_filename=chunk.document_filename,
            )
            for i, (chunk, _) in enumerate(self._pending)
        ]
        self._inner.add_chunks(compressed_chunks)

    @staticmethod
    def _hash_pca(pca: PCA) -> str:
        """SHA-256 dos componentes principais para rastreabilidade."""
        components_bytes = pca.components_.tobytes()
        return hashlib.sha256(components_bytes).hexdigest()
