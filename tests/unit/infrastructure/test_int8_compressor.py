"""Testes unit do Int8Compressor."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from docuvector.domain.enums import CompressionMethod
from docuvector.infrastructure.compression.int8_compressor import Int8Compressor


def _random_matrix(n: int, d: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed=seed)
    return rng.standard_normal((n, d)).astype(np.float32)


@pytest.mark.unit
class TestInt8Compressor:
    def test_method_name(self) -> None:
        assert Int8Compressor().method_name is CompressionMethod.INT8

    def test_bytes_per_element_int8(self) -> None:
        assert Int8Compressor().bytes_per_element == 1.0

    def test_output_dtype_int8(self) -> None:
        x = _random_matrix(n=10, d=64)
        c = Int8Compressor()
        assert c.transform(x).dtype == np.int8

    def test_output_shape_preservada(self) -> None:
        """Int8 não reduz dimensão: shape deve ser igual à entrada."""
        x = _random_matrix(n=10, d=64)
        c = Int8Compressor()
        assert c.transform(x).shape == (10, 64)

    def test_valores_no_range_int8(self) -> None:
        x = _random_matrix(n=20, d=128)
        c = Int8Compressor()
        out = c.transform(x)
        assert int(out.min()) >= -127
        assert int(out.max()) <= 127

    def test_transform_sem_fit_nao_levanta(self) -> None:
        """Int8 é stateless: transform sem fit deve funcionar normalmente."""
        x = _random_matrix(n=5, d=32)
        c = Int8Compressor()
        out = c.transform(x)
        assert out.shape == (5, 32)

    def test_target_dim_none_antes_de_fit(self) -> None:
        """Antes de fit/transform, target_dim deve ser None (não 0)."""
        assert Int8Compressor().target_dim is None

    def test_fit_atualiza_target_dim(self) -> None:
        x = _random_matrix(n=10, d=64)
        c = Int8Compressor()
        c.fit(x)
        assert c.target_dim == 64

    def test_vetor_nulo_nao_causa_nan(self) -> None:
        """Vetor todo zeros deve ser quantizado como zeros (sem divisão por zero)."""
        x = np.zeros((5, 32), dtype=np.float32)
        c = Int8Compressor()
        out = c.transform(x)
        assert not np.any(np.isnan(out.astype(np.float32)))
        assert np.all(out == 0)

    def test_sinal_preservado(self) -> None:
        """Componentes positivas devem virar positivas; negativas, negativas."""
        x = np.array([[1.0, -2.0, 0.5, -0.1]], dtype=np.float32)
        c = Int8Compressor()
        out = c.transform(x)
        assert out[0, 0] > 0  # 1.0 positivo
        assert out[0, 1] < 0  # -2.0 negativo

    @given(
        n=st.integers(min_value=2, max_value=50),
        d=st.integers(min_value=4, max_value=256),
    )
    @settings(max_examples=80)
    def test_valores_sempre_no_range(self, n: int, d: int) -> None:
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        out = Int8Compressor().transform(x)
        assert int(out.min()) >= -127
        assert int(out.max()) <= 127

    @given(
        n=st.integers(min_value=2, max_value=50),
        d=st.integers(min_value=4, max_value=256),
    )
    @settings(max_examples=80)
    def test_shape_preservada_invariante(self, n: int, d: int) -> None:
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        out = Int8Compressor().transform(x)
        assert out.shape == (n, d)
