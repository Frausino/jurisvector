"""Contrato para armazenamento e busca vetorial."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from docuvector.domain.entities import RetrievedChunk
from docuvector.domain.interfaces.embedding_provider import EmbeddingVector


@dataclass(frozen=True, slots=True)
class ChunkVector:
    """Pacote (chunk + vetor) entregue ao VectorStore para indexação."""

    chunk_id: UUID
    document_id: UUID
    owner_id: UUID
    chunk_index: int
    text: str
    embedding: EmbeddingVector
    document_filename: str


class VectorStore(Protocol):
    """Armazena vetores e responde queries por similaridade.

    Toda assinatura recebe `owner_id`: o store NUNCA expõe um método
    que ignore o dono. Defesa contra BOLA built-in no contrato.
    """

    def add_chunks(self, chunks: Sequence[ChunkVector]) -> None:
        """Indexa um lote de chunks vetorizados."""
        ...

    def search(
        self,
        owner_id: UUID,
        query_embedding: EmbeddingVector,
        top_k: int,
        similarity_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Busca chunks similares pertencentes ao dono informado.

        Resultados abaixo de `similarity_threshold` são descartados.
        Ordenação: similaridade decrescente.
        """
        ...

    def delete_document(self, owner_id: UUID, document_id: UUID) -> int:
        """Remove todos os chunks de um documento; devolve quantidade apagada."""
        ...
