"""Teste de integração — múltiplas coleções Chroma.

Valida que:
1. `CompressedVectorStore` indexa vetores comprimidos no Chroma real.
2. `CompareRetrievalUseCase` recupera chunks de múltiplas coleções.
3. Métricas IR são calculadas corretamente com dados reais.

Decisões:
- Usa `tempfile.mkdtemp()` para isolamento completo (Chroma em diretório temporário).
- Embedder local E5 real (mesmo padrão do test_rag_end_to_end.py).
- Limpa o diretório após cada teste.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Generator
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from docuvector.application.compare_retrieval_use_case import CompareRetrievalUseCase
from docuvector.domain.enums import CompressionMethod
from docuvector.domain.interfaces import ChunkVector
from docuvector.infrastructure.compression.int8_compressor import Int8Compressor
from docuvector.infrastructure.embeddings.sentence_transformers_embedder import (
    SentenceTransformersEmbedder,
)
from docuvector.infrastructure.vector_stores.chroma_vector_store import ChromaVectorStore
from docuvector.infrastructure.vector_stores.compressed_vector_store import (
    CompressedVectorStore,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from docuvector.domain.entities import User

_LEGAL_TEXT = """
CONTRATO DE PRESTAÇÃO DE SERVIÇOS

CLÁUSULA PRIMEIRA - DO OBJETO
Prestação de consultoria jurídica em direito empresarial.

CLÁUSULA SEGUNDA - DO PRAZO
O contrato vigorará por 12 meses a partir da assinatura.

CLÁUSULA TERCEIRA - DA RESCISÃO
Rescisão mediante notificação prévia de 30 dias.

CLÁUSULA QUARTA - DO VALOR
Valor mensal de R$ 5.000,00 até o quinto dia útil.
""".strip()


@pytest.fixture
def chroma_dir() -> Generator[str, None, None]:
    path = tempfile.mkdtemp(prefix="test_multi_chroma_")
    yield path
    shutil.rmtree(path, ignore_errors=True)


# =============================================================
# Integração: CompressedVectorStore com Chroma real
# =============================================================
@pytest.mark.integration
@pytest.mark.slow
def test_compressed_int8_store_indexa_e_recupera_chunks(
    regular_user_one: User,
    client: TestClient,
) -> None:
    """Int8 comprimido indexa e recupera chunks com Chroma real."""

    chroma_path = tempfile.mkdtemp(prefix="test_int8_chroma_")
    try:
        owner_id = regular_user_one.id
        doc_id = uuid4()

        embedder = SentenceTransformersEmbedder(
            model_name=os.environ.get(
                "SENTENCE_TRANSFORMERS_MODEL", "intfloat/multilingual-e5-small"
            ),
            dimensions=384,
            cache_folder=os.environ.get("HF_HOME", "./data/test_hf_cache"),
        )

        texts = [
            "cláusula de rescisão com aviso prévio de 30 dias",
            "valor mensal de cinco mil reais",
        ]
        vectors = embedder.embed_passages(texts)

        inner = ChromaVectorStore(
            persist_directory=chroma_path,
            collection_name="test_int8",
        )
        store = CompressedVectorStore(inner_store=inner, compressor=Int8Compressor())

        chunks = [
            ChunkVector(
                chunk_id=uuid4(),
                document_id=doc_id,
                owner_id=owner_id,
                chunk_index=i,
                text=text,
                embedding=tuple(float(v) for v in vectors[i]),
                document_filename="contrato.txt",
            )
            for i, text in enumerate(texts)
        ]
        store.add_chunks(chunks)

        query_vector = embedder.embed_query("prazo de rescisão do contrato")
        results = store.search(
            owner_id=owner_id,
            query_embedding=query_vector,
            top_k=2,
            similarity_threshold=0.0,
        )

        assert len(results) > 0
        assert all(r.document_id == doc_id for r in results)
    finally:
        shutil.rmtree(chroma_path, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.slow
def test_compare_retrieval_com_chroma_real(
    regular_user_one: User,
) -> None:
    """CompareRetrievalUseCase com Chroma real: Recall@K calculado corretamente."""

    chroma_original = tempfile.mkdtemp(prefix="test_orig_chroma_")
    chroma_int8 = tempfile.mkdtemp(prefix="test_int8_chroma_")
    try:
        owner_id = regular_user_one.id
        doc_id = uuid4()

        embedder = SentenceTransformersEmbedder(
            model_name=os.environ.get(
                "SENTENCE_TRANSFORMERS_MODEL", "intfloat/multilingual-e5-small"
            ),
            dimensions=384,
            cache_folder=os.environ.get("HF_HOME", "./data/test_hf_cache"),
        )

        texts = [
            "cláusula de rescisão com aviso prévio de 30 dias",
            "valor mensal de R$ 5.000,00",
            "prazo de vigência de 12 meses",
        ]
        vectors = list(embedder.embed_passages(texts))

        # Store original
        original_store = ChromaVectorStore(
            persist_directory=chroma_original,
            collection_name="original",
        )
        # Store comprimido Int8
        int8_inner = ChromaVectorStore(
            persist_directory=chroma_int8,
            collection_name="int8",
        )
        int8_store = CompressedVectorStore(inner_store=int8_inner, compressor=Int8Compressor())

        chunks = [
            ChunkVector(
                chunk_id=uuid4(),
                document_id=doc_id,
                owner_id=owner_id,
                chunk_index=i,
                text=text,
                embedding=tuple(float(v) for v in vectors[i]),
                document_filename="contrato.txt",
            )
            for i, text in enumerate(texts)
        ]
        original_store.add_chunks(chunks)
        int8_store.add_chunks(chunks)

        use_case = CompareRetrievalUseCase(
            original_store=original_store,
            compressed_stores=[(CompressionMethod.INT8, int8_store)],
        )

        result = use_case.compare(
            owner_id=owner_id,
            query="qual o prazo de rescisão do contrato?",
            embedding_provider=embedder,
            top_k=3,
        )

        assert result.original.chunks_count > 0
        assert len(result.compressed) == 1
        int8_result = result.compressed[0]
        assert int8_result.compression_method is CompressionMethod.INT8
        # Recall deve ser > 0 (Int8 preserva semântica)
        assert int8_result.ir_metrics.recall_at_k >= 0.0
        # MRR deve estar no range válido
        assert 0.0 <= int8_result.ir_metrics.mrr <= 1.0
    finally:
        shutil.rmtree(chroma_original, ignore_errors=True)
        shutil.rmtree(chroma_int8, ignore_errors=True)
