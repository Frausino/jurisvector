"""Vector store baseado em ChromaDB (modo persistente local).

Defesa contra BOLA: TODA operação obriga `owner_id`. O ChromaDB
suporta filtros `where` no metadata; usamos isso para garantir
isolamento entre tenants no nível do storage. Não há método que ignore
o dono.

Decisão arquitetural: uma única collection por provedor de embeddings
(`docuvector_openai` ou `docuvector_st`). Vetores de provedores
diferentes têm dimensões distintas (1536 vs 384) e não podem coexistir
na mesma collection. O `IngestionUseCase` recebe o vector store e o
embedder juntos, garantindo coerência.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

import chromadb
import numpy as np
from chromadb.api.types import IncludeEnum
from chromadb.config import Settings as ChromaSettings
from numpy.typing import NDArray

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.exceptions import VectorStoreError
from docuvector.domain.interfaces import ChunkVector
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector

if TYPE_CHECKING:
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection


class ChromaVectorStore:
    """Implementa `VectorStore` com ChromaDB persistente.

    Anotações importantes:
    - `add_chunks` adiciona `owner_id`, `document_id`, `chunk_index`,
      `text` e `document_filename` em metadata. Nenhum dado sensível
      ALÉM do texto do chunk vai para o Chroma.
    - `search` exige `owner_id` e o aplica como filtro `where`. NÃO há
      método de busca sem owner.
    - `delete_document` exige owner_id + document_id em conjunto.
    """

    def __init__(self, persist_directory: str, collection_name: str) -> None:
        self._collection_name = collection_name
        self._client = self._build_client(persist_directory)
        self._collection: Collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # -------------------------------------------------------------
    # Operações
    # -------------------------------------------------------------
    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        """Indexa um lote de chunks vetorizados."""
        if not chunks:
            return

        ids: list[str] = []
        embeddings: list[Sequence[float] | Sequence[int]] = []
        metadatas: list[Mapping[str, str | int | float | bool]] = []
        documents_text: list[str] = []

        for chunk in chunks:
            ids.append(str(chunk.chunk_id))
            embeddings.append(list(chunk.embedding))
            documents_text.append(chunk.text)
            metadata: dict[str, str | int | float | bool] = {
                "owner_id": str(chunk.owner_id),
                "document_id": str(chunk.document_id),
                "chunk_index": chunk.chunk_index,
                "document_filename": chunk.document_filename,
            }
            metadatas.append(metadata)

        try:
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents_text,
            )
        except Exception as chroma_failure:
            raise VectorStoreError(
                f"Falha ao indexar chunks no Chroma: {chroma_failure}"
            ) from chroma_failure

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Busca chunks similares, sempre filtrando por dono."""
        if top_k <= 0:
            return []

        try:
            query_embeddings: list[Sequence[float] | Sequence[int]] = []
            query_embeddings.append(list(query_embedding))
            results = self._collection.query(
                query_embeddings=query_embeddings,
                n_results=top_k,
                where={"owner_id": str(owner_id)},
            )
        except Exception as chroma_failure:
            raise VectorStoreError(f"Falha na busca vetorial: {chroma_failure}") from chroma_failure

        return self._materialize_results(results, similarity_threshold)

    def get_vectors_for_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> NDArray[np.float32]:
        """Recupera a matriz de embeddings de um documento do ChromaDB.

        Usa filtro composto `owner_id + document_id` para defesa BOLA:
        mesmo que o chamador conheça o UUID do documento, só obtém os
        vetores se for o dono.

        Raises:
            VectorStoreError: se não houver vetores ou a operação falhar.
        """
        where_clause: dict[str, Any] = {
            "$and": [
                {"owner_id": {"$eq": str(owner_id)}},
                {"document_id": {"$eq": str(document_id)}},
            ]
        }

        try:
            result = self._collection.get(
                where=where_clause,
                include=[IncludeEnum.embeddings],
            )
        except Exception as chroma_failure:
            raise VectorStoreError(
                f"Falha ao recuperar vetores do documento {document_id}: {chroma_failure}"
            ) from chroma_failure

        raw_embeddings = result.get("embeddings")

        if raw_embeddings is None:
            raise VectorStoreError(
                f"Documento {document_id} não possui vetores indexados "
                f"ou não pertence ao owner {owner_id}."
            )

        embeddings = np.asarray(raw_embeddings, dtype=np.float32)

        if embeddings.size == 0:
            raise VectorStoreError(
                f"Documento {document_id} não possui vetores indexados "
                f"ou não pertence ao owner {owner_id}."
            )

        return embeddings

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        """Apaga chunks de um documento, mantendo isolamento por dono."""
        where_clause: dict[str, Any] = {
            "$and": [
                {"owner_id": {"$eq": str(owner_id)}},
                {"document_id": {"$eq": str(document_id)}},
            ]
        }
        try:
            matching = self._collection.get(where=where_clause)
            chunk_ids_to_delete = matching.get("ids") or []
            if not chunk_ids_to_delete:
                return 0
            self._collection.delete(ids=chunk_ids_to_delete)
        except Exception as chroma_failure:
            raise VectorStoreError(f"Falha ao apagar chunks: {chroma_failure}") from chroma_failure
        return len(chunk_ids_to_delete)

    # -------------------------------------------------------------
    # Helpers internos
    # -------------------------------------------------------------
    @staticmethod
    def _build_client(persist_directory: str) -> ClientAPI:
        """Cria o cliente ChromaDB em modo persistente local.

        Telemetria desabilitada por padrão (nada de phone-home do
        Chroma para o sistema do TCC).
        """
        return chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
        )

    @staticmethod
    def _materialize_results(
        raw_results: Any,
        similarity_threshold: float,
    ) -> list[RetrievedChunk]:
        """Converte resposta do Chroma em entidades `RetrievedChunk`.

        Chroma devolve `distances` (coseno, 0 = idêntico, 2 = oposto).
        Convertemos para similaridade em [0, 1] como `1 - distance/2`.
        Resultados abaixo do threshold são descartados.
        """
        ids_matrix = raw_results.get("ids") or [[]]
        distances_matrix = raw_results.get("distances") or [[]]
        documents_matrix = raw_results.get("documents") or [[]]
        metadatas_matrix = raw_results.get("metadatas") or [[]]

        if not ids_matrix or not ids_matrix[0]:
            return []

        retrieved: list[RetrievedChunk] = []
        for chunk_id, distance, document_text, metadata in zip(
            ids_matrix[0],
            distances_matrix[0],
            documents_matrix[0],
            metadatas_matrix[0],
            strict=False,
        ):
            similarity = max(0.0, 1.0 - (float(distance) / 2.0))
            if similarity < similarity_threshold:
                continue
            retrieved.append(
                RetrievedChunk(
                    chunk_id=UUID(chunk_id),
                    document_id=UUID(str(metadata["document_id"])),
                    document_filename=str(metadata.get("document_filename", "")),
                    text=document_text or "",
                    similarity=similarity,
                    chunk_index=int(metadata.get("chunk_index", 0)),
                )
            )
        return retrieved
