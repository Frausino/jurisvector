"""Testes unit do RandomProjectionCompressor."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from docuvector.domain.enums import CompressionMethod
from docuvector.infrastructure.compression.random_projection_compressor import (
    RandomProjectionCompressor,
)


def _random_matrix(n: int, d: int) -> np.ndarray:
    rng = np.random.default_rng(seed=42)
    return rng.standard_normal((n, d)).astype(np.float32)


@pytest.mark.unit
class TestRandomProjectionCompressor:
    def test_method_name(self) -> None:
        assert (
            RandomProjectionCompressor(target_dim=64).method_name
            is CompressionMethod.RANDOM_PROJECTION
        )

    def test_bytes_per_element_float32(self) -> None:
        assert RandomProjectionCompressor(target_dim=64).bytes_per_element == 4.0

    def test_output_shape(self) -> None:
        x = _random_matrix(n=20, d=128)
        c = RandomProjectionCompressor(target_dim=64)
        c.fit(x)
        assert c.transform(x).shape == (20, 64)

    def test_output_dtype_float32(self) -> None:
        x = _random_matrix(n=20, d=128)
        c = RandomProjectionCompressor(target_dim=64)
        c.fit(x)
        assert c.transform(x).dtype == np.float32

    def test_target_dim_property(self) -> None:
        assert RandomProjectionCompressor(target_dim=48).target_dim == 48

    def test_transform_before_fit_raises(self) -> None:
        c = RandomProjectionCompressor(target_dim=32)
        with pytest.raises(RuntimeError, match="fit"):
            c.transform(_random_matrix(n=5, d=64))

    def test_fit_raises_when_target_dim_greater_than_input_dim(self) -> None:
        """target_dim maior que dimensão de entrada deve falhar no fit."""
        x = _random_matrix(n=20, d=64)
        c = RandomProjectionCompressor(target_dim=512)
        with pytest.raises(ValueError, match="target_dim"):
            c.fit(x)

    def test_reprodutivel_com_random_state_fixo(self) -> None:
        """Dois fits com mesmos dados devem produzir mesma projeção."""
        x = _random_matrix(n=20, d=128)
        c1 = RandomProjectionCompressor(target_dim=64)
        c2 = RandomProjectionCompressor(target_dim=64)
        c1.fit(x)
        c2.fit(x)
        np.testing.assert_array_equal(c1.transform(x), c2.transform(x))

    @given(
        n=st.integers(min_value=5, max_value=60),
        d=st.integers(min_value=8, max_value=128),
    )
    @settings(max_examples=40)
    def test_compressed_dim_le_original(self, n: int, d: int) -> None:
        target = max(2, d // 2)
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        c = RandomProjectionCompressor(target_dim=target)
        c.fit(x)
        assert c.transform(x).shape[1] <= d

    @given(
        n=st.integers(min_value=5, max_value=60),
        d=st.integers(min_value=8, max_value=128),
    )
    @settings(max_examples=40)
    def test_output_is_finite(self, n: int, d: int) -> None:
        target = max(2, d // 2)
        rng = np.random.default_rng(0)
        x = rng.standard_normal((n, d)).astype(np.float32)
        c = RandomProjectionCompressor(target_dim=target)
        c.fit(x)
        assert np.all(np.isfinite(c.transform(x)))
