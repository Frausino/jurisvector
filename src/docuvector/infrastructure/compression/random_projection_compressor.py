"""Compressor de embeddings via Random Projection gaussiana.

Trade-off: fit muito mais rápido que PCA (sem decomposição SVD), com retenção
semântica levemente inferior. Preserva distâncias aproximadamente pelo
Johnson-Lindenstrauss lemma.

Implementação:
- `sklearn.random_projection.GaussianRandomProjection`.
- Saída: float32. bytes_per_element = 4.0.
- Redução de dimensão: original_dim → target_dim.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import NDArray
from sklearn.random_projection import GaussianRandomProjection

from docuvector.domain.enums import CompressionMethod


class RandomProjectionCompressor:
    """Implementa `Compressor` via sklearn GaussianRandomProjection."""

    _BYTES_PER_ELEMENT: float = 4.0  # float32

    def __init__(self, target_dim: int) -> None:
        self._target_dim = target_dim
        self._projector: GaussianRandomProjection | None = None

    @property
    def method_name(self) -> CompressionMethod:
        return CompressionMethod.RANDOM_PROJECTION

    @property
    def target_dim(self) -> int:
        return self._target_dim

    @property
    def bytes_per_element(self) -> float:
        return self._BYTES_PER_ELEMENT

    def fit(self, vectors: np.ndarray) -> None:
        """Gera a matriz de projeção aleatória ajustada aos dados.

        Args:
            vectors: Matriz (n_samples, n_dims) de embeddings float32.
        """
        n_dims = vectors.shape[1]
        if self._target_dim > n_dims:
            raise ValueError(
                f"RandomProjection: target_dim ({self._target_dim}) não pode ser "
                f"maior que a dimensão de entrada ({n_dims})."
            )
        self._projector = GaussianRandomProjection(
            n_components=self._target_dim,
            random_state=42,  # reprodutibilidade entre execuções
        )
        self._projector.fit(vectors.astype(np.float32))

    def transform(self, vectors: np.ndarray) -> np.ndarray:
        """Projeta vetores via matriz gaussiana aleatória.

        Raises:
            RuntimeError: se chamado antes de `fit`.
        """
        if self._projector is None:
            raise RuntimeError(
                "RandomProjectionCompressor.fit() deve ser chamado antes de transform()."
            )
        compressed = self._projector.transform(vectors.astype(np.float32)).astype(np.float32)

        return cast(
            NDArray[np.float32],
            compressed,
        )
