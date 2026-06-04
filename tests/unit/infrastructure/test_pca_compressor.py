"""Testes unit do PcaCompressor."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from docuvector.domain.enums import CompressionMethod
from docuvector.infrastructure.compression.pca_compressor import PcaCompressor


def _random_matrix(n: int, d: int) -> np.ndarray:
    rng = np.random.default_rng(seed=42)
    return rng.standard_normal((n, d)).astype(np.float32)


@pytest.mark.unit
class TestPcaCompressor:
    def test_method_name(self) -> None:
        assert PcaCompressor(target_dim=64).method_name is CompressionMethod.PCA

    def test_bytes_per_element_float32(self) -> None:
        assert PcaCompressor(target_dim=64).bytes_per_element == 4.0

    def test_output_shape(self) -> None:
        x = _random_matrix(n=128, d=128)
        c = PcaCompressor(target_dim=64)
        c.fit(x)
        out = c.transform(x)

        assert out.shape == (128, 64)

    def test_output_dtype_float32(self) -> None:
        x = _random_matrix(n=128, d=128)
        c = PcaCompressor(target_dim=64)
        c.fit(x)
        assert c.transform(x).dtype == np.float32

    def test_target_dim_property(self) -> None:
        assert PcaCompressor(target_dim=32).target_dim == 32

    def test_transform_before_fit_raises(self) -> None:
        x = _random_matrix(n=10, d=64)
        c = PcaCompressor(target_dim=32)
        with pytest.raises(RuntimeError, match="fit"):
            c.transform(x)

    def test_fit_raises_when_n_samples_less_than_target_dim(self) -> None:
        x = _random_matrix(n=5, d=64)
        c = PcaCompressor(target_dim=32)
        with pytest.raises(ValueError, match="n_samples"):
            c.fit(x)

    def test_fit_raises_when_target_dim_greater_than_input_dim(self) -> None:
        """target_dim=512 com vetores de 128 dims deve falhar no fit."""
        x = _random_matrix(n=20, d=128)
        c = PcaCompressor(target_dim=512)
        with pytest.raises(ValueError, match="target_dim"):
            c.fit(x)

    def test_different_batches_same_fit(self) -> None:
        """transform em batch diferente do fit não deve levantar exceção."""
        x_fit = _random_matrix(n=128, d=128)
        x_new = _random_matrix(n=5, d=128)
        c = PcaCompressor(target_dim=64)
        c.fit(x_fit)
        out = c.transform(x_new)
        assert out.shape == (5, 64)

    @given(
        n=st.integers(min_value=10, max_value=60),
        d=st.integers(min_value=8, max_value=64),
    )
    @settings(max_examples=40)
    def test_compressed_dim_le_original(self, n: int, d: int) -> None:
        target = max(2, d // 2)
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        if n < target:
            return
        c = PcaCompressor(target_dim=target)
        c.fit(x)
        out = c.transform(x)
        assert out.shape[1] <= d

    @given(
        n=st.integers(min_value=10, max_value=60),
        d=st.integers(min_value=8, max_value=64),
    )
    @settings(max_examples=40)
    def test_output_is_finite(self, n: int, d: int) -> None:
        target = max(2, d // 2)
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        if n < target:
            return
        c = PcaCompressor(target_dim=target)
        c.fit(x)
        assert np.all(np.isfinite(c.transform(x)))
