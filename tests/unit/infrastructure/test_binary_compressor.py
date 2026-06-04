"""Testes unit do BinaryCompressor."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from docuvector.domain.enums import CompressionMethod
from docuvector.infrastructure.compression.binary_compressor import BinaryCompressor


def _random_matrix(n: int, d: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed=seed)
    return rng.standard_normal((n, d)).astype(np.float32)


@pytest.mark.unit
class TestBinaryCompressor:
    def test_method_name(self) -> None:
        assert BinaryCompressor().method_name is CompressionMethod.BINARY

    def test_bytes_per_element_binario(self) -> None:
        assert BinaryCompressor().bytes_per_element == 0.125

    def test_output_dtype_uint8(self) -> None:
        x = _random_matrix(n=10, d=64)
        assert BinaryCompressor().transform(x).dtype == np.uint8

    def test_output_shape_preservada(self) -> None:
        x = _random_matrix(n=10, d=64)
        assert BinaryCompressor().transform(x).shape == (10, 64)

    def test_valores_apenas_zero_ou_um(self) -> None:
        x = _random_matrix(n=20, d=128)
        out = BinaryCompressor().transform(x)
        unique_values = set(np.unique(out).tolist())
        assert unique_values.issubset({0, 1})

    def test_positivos_viram_um(self) -> None:
        x = np.array([[1.0, 2.0, 0.5]], dtype=np.float32)
        out = BinaryCompressor().transform(x)
        assert np.all(out == 1)

    def test_negativos_viram_zero(self) -> None:
        x = np.array([[-1.0, -0.1, -5.0]], dtype=np.float32)
        out = BinaryCompressor().transform(x)
        assert np.all(out == 0)

    def test_zero_exato_vira_zero(self) -> None:
        """Limiar: v > 0 → 1, v ≤ 0 → 0. Zero deve virar 0."""
        x = np.array([[0.0, 1.0, -1.0]], dtype=np.float32)
        out = BinaryCompressor().transform(x)
        assert out[0, 0] == 0  # zero → 0
        assert out[0, 1] == 1  # positivo → 1
        assert out[0, 2] == 0  # negativo → 0

    def test_transform_sem_fit_funciona(self) -> None:
        """Binary é stateless: não exige fit antes do transform."""
        x = _random_matrix(n=5, d=32)
        out = BinaryCompressor().transform(x)
        assert out.shape == (5, 32)

    def test_target_dim_none_antes_de_fit(self) -> None:
        """Antes de fit/transform, target_dim deve ser None (não 0)."""
        assert BinaryCompressor().target_dim is None

    def test_fit_atualiza_target_dim(self) -> None:
        x = _random_matrix(n=10, d=64)
        c = BinaryCompressor()
        c.fit(x)
        assert c.target_dim == 64

    @given(
        n=st.integers(min_value=2, max_value=50),
        d=st.integers(min_value=4, max_value=256),
    )
    @settings(max_examples=80)
    def test_valores_apenas_0_ou_1_invariante(self, n: int, d: int) -> None:
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        out = BinaryCompressor().transform(x)
        assert set(np.unique(out).tolist()).issubset({0, 1})

    @given(
        n=st.integers(min_value=2, max_value=50),
        d=st.integers(min_value=4, max_value=256),
    )
    @settings(max_examples=80)
    def test_shape_preservada_invariante(self, n: int, d: int) -> None:
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        out = BinaryCompressor().transform(x)
        assert out.shape == (n, d)
