"""Testes unit do domínio — Bloco 1 (Sprint 4A).

Cobre:
- CompressionMetrics: cálculo de ratio_bytes e space_savings_pct
- Invariantes matemáticos via hypothesis
- Compressor como @runtime_checkable Protocol
- Document com campos opcionais de compressão
"""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from docuvector.domain.entities.compression_metrics import CompressionMetrics
from docuvector.domain.entities.document import Document
from docuvector.domain.enums import CompressionMethod, FileFormat
from docuvector.domain.interfaces.compressor import Compressor


# =============================================================
# Helpers de fábrica
# =============================================================
def _make_metrics(
    method: CompressionMethod = CompressionMethod.PCA,
    original_dim: int = 384,
    compressed_dim: int = 192,
    bytes_per_element: float = 4.0,
    semantic_retention: float = 0.97,
    n_vectors: int = 10,
    fit_time_ms: int = 50,
    transform_time_ms: int = 10,
) -> CompressionMetrics:
    return CompressionMetrics(
        method=method,
        original_dim=original_dim,
        compressed_dim=compressed_dim,
        bytes_per_element=bytes_per_element,
        fit_time_ms=fit_time_ms,
        transform_time_ms=transform_time_ms,
        semantic_retention=semantic_retention,
        n_vectors=n_vectors,
    )


# =============================================================
# CompressionMetrics — campos derivados
# =============================================================
@pytest.mark.unit
class TestCompressionMetricsDerivados:
    def test_pca_metade_dim_ratio_dois(self) -> None:
        """PCA 384→192 (float32→float32): ratio deve ser 2.0."""
        m = _make_metrics(original_dim=384, compressed_dim=192, bytes_per_element=4.0)
        assert m.ratio_bytes == pytest.approx(2.0)

    def test_pca_metade_dim_savings_cinquenta_pct(self) -> None:
        m = _make_metrics(original_dim=384, compressed_dim=192, bytes_per_element=4.0)
        assert m.space_savings_pct == pytest.approx(50.0)

    def test_int8_sem_reducao_ratio_quatro(self) -> None:
        """Int8 sem redução de dimensão: float32(4B) → int8(1B) = ratio 4.0."""
        m = _make_metrics(original_dim=384, compressed_dim=384, bytes_per_element=1.0)
        assert m.ratio_bytes == pytest.approx(4.0)

    def test_int8_savings_setenta_e_cinco_pct(self) -> None:
        m = _make_metrics(original_dim=384, compressed_dim=384, bytes_per_element=1.0)
        assert m.space_savings_pct == pytest.approx(75.0)

    def test_binary_sem_reducao_ratio_trinta_e_dois(self) -> None:
        """Binary (0.125 B/elem): float32(4B) / 0.125B = ratio 32.0."""
        m = _make_metrics(original_dim=384, compressed_dim=384, bytes_per_element=0.125)
        assert m.ratio_bytes == pytest.approx(32.0)

    def test_binary_savings_noventa_e_tres_pct(self) -> None:
        m = _make_metrics(original_dim=384, compressed_dim=384, bytes_per_element=0.125)
        assert m.space_savings_pct == pytest.approx(96.875)

    def test_pca_openai_1536_para_384_ratio_quatro(self) -> None:
        """Caso representativo para a banca: OpenAI 1536→384, 75% de economia."""
        m = _make_metrics(original_dim=1536, compressed_dim=384, bytes_per_element=4.0)
        assert m.ratio_bytes == pytest.approx(4.0)
        assert m.space_savings_pct == pytest.approx(75.0)

    def test_campos_derivados_sao_imutaveis(self) -> None:
        """frozen=True: nenhum campo pode ser alterado após criação."""
        m = _make_metrics()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            m.ratio_bytes = 99.0  # type: ignore[misc]

    def test_storage_bytes_correto(self) -> None:
        m = _make_metrics(compressed_dim=192, bytes_per_element=4.0)
        assert m.storage_bytes(n_chunks=100) == 100 * 192 * 4

    def test_original_storage_bytes_correto(self) -> None:
        m = _make_metrics(original_dim=384)
        assert m.original_storage_bytes(n_chunks=100) == 100 * 384 * 4


# =============================================================
# CompressionMetrics — invariantes via hypothesis
# =============================================================
@pytest.mark.unit
class TestCompressionMetricsInvariantes:
    @given(
        original_dim=st.integers(min_value=2, max_value=2048),
        compressed_dim=st.integers(min_value=1, max_value=2048),
        bytes_per_element=st.sampled_from([4.0, 1.0, 0.125]),
    )
    @settings(max_examples=200)
    def test_ratio_bytes_sempre_positivo(
        self,
        original_dim: int,
        compressed_dim: int,
        bytes_per_element: float,
    ) -> None:
        m = _make_metrics(
            original_dim=original_dim,
            compressed_dim=compressed_dim,
            bytes_per_element=bytes_per_element,
        )
        assert m.ratio_bytes > 0.0

    @given(
        original_dim=st.integers(min_value=2, max_value=2048),
        compressed_dim=st.integers(min_value=1, max_value=2048),
        bytes_per_element=st.sampled_from([4.0, 1.0, 0.125]),
    )
    @settings(max_examples=200)
    def test_space_savings_nunca_maior_que_100(
        self,
        original_dim: int,
        compressed_dim: int,
        bytes_per_element: float,
    ) -> None:
        m = _make_metrics(
            original_dim=original_dim,
            compressed_dim=compressed_dim,
            bytes_per_element=bytes_per_element,
        )
        # Quando compressed_dim > original_dim, space_savings pode ser negativo
        # (expansão); nunca deve ser > 100%.
        assert m.space_savings_pct <= 100.0

    @given(
        semantic_retention=st.floats(min_value=0.0, max_value=1.0),
        threshold=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=100)
    def test_lossless_threshold_consistente(
        self,
        semantic_retention: float,
        threshold: float,
    ) -> None:
        m = _make_metrics(semantic_retention=semantic_retention)
        resultado = m.is_lossless_threshold(min_retention=threshold)
        assert resultado == (semantic_retention >= threshold)


# =============================================================
# Compressor Protocol
# =============================================================
@pytest.mark.unit
class TestCompressorProtocol:
    def test_objeto_sem_interface_nao_e_compressor(self) -> None:
        """Objeto sem os métodos corretos não passa no isinstance."""

        class NaoECompressor:
            pass

        assert not isinstance(NaoECompressor(), Compressor)

    def test_objeto_com_interface_completa_e_compressor(self) -> None:
        """Implementação mínima que satisfaz o Protocol."""

        class CompressorFake:
            @property
            def method_name(self) -> CompressionMethod:
                return CompressionMethod.PCA

            @property
            def target_dim(self) -> int:
                return 192

            @property
            def bytes_per_element(self) -> float:
                return 4.0

            def fit(self, vectors: np.ndarray) -> None:
                pass

            def transform(self, vectors: np.ndarray) -> np.ndarray:
                return vectors[:, : self.target_dim]

        assert isinstance(CompressorFake(), Compressor)


# =============================================================
# Document com campos opcionais de compressão
# =============================================================
@pytest.mark.unit
class TestDocumentCamposCompressao:
    def test_document_criado_sem_campos_compressao(self) -> None:
        """Campos de compressão devem ser None por default."""

        doc = Document(
            owner_id=uuid4(),
            filename="contrato.pdf",
            file_format=FileFormat.PDF,
            size_bytes=1024,
            checksum_sha256="abc123",
        )
        assert doc.compression_method is None
        assert doc.original_dimension is None
        assert doc.compressed_dimension is None
        assert doc.semantic_retention is None
        assert doc.ingest_time_ms is None

    def test_dataclasses_replace_preserva_campos_compressao(self) -> None:
        """dataclasses.replace deve funcionar para atualizar campos frozen."""

        doc = Document(
            owner_id=uuid4(),
            filename="contrato.pdf",
            file_format=FileFormat.PDF,
            size_bytes=1024,
            checksum_sha256="abc123",
        )
        doc_com_compressao = dataclasses.replace(
            doc,
            compression_method=CompressionMethod.PCA,
            original_dimension=384,
            compressed_dimension=192,
            semantic_retention=0.97,
            ingest_time_ms=1200,
        )

        assert doc_com_compressao.compression_method is CompressionMethod.PCA
        assert doc_com_compressao.original_dimension == 384
        assert doc_com_compressao.compressed_dimension == 192
        assert doc_com_compressao.semantic_retention == pytest.approx(0.97)
        # documento original permanece inalterado (frozen)
        assert doc.compression_method is None
