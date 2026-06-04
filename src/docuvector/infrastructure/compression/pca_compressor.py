"""Compressor de embeddings via PCA (Análise de Componentes Principais).

Trade-off: melhor retenção semântica entre os 4 compressores, ao custo de
ser stateful (requer fit em batch) e mais lento no fit que RandomProjection.

Implementação:
- `sklearn.decomposition.PCA` com `svd_solver="full"` para máxima precisão.
- Saída: float32 (mesmo dtype da entrada). bytes_per_element = 4.0.
- Redução de dimensão: original_dim → target_dim (ex.: 384 → 192).
"""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import NDArray
from sklearn.decomposition import PCA

from docuvector.domain.enums import CompressionMethod


class PcaCompressor:
    """Implementa `Compressor` via sklearn PCA."""

    _BYTES_PER_ELEMENT: float = 4.0  # float32

    def __init__(self, target_dim: int) -> None:
        self._target_dim = target_dim
        self._pca: PCA | None = None

    @property
    def method_name(self) -> CompressionMethod:
        return CompressionMethod.PCA

    @property
    def target_dim(self) -> int:
        return self._target_dim

    @property
    def bytes_per_element(self) -> float:
        return self._BYTES_PER_ELEMENT

    def fit(self, vectors: np.ndarray) -> None:
        """Ajusta o PCA à distribuição dos vetores de entrada.

        Args:
            vectors: Matriz (n_samples, n_dims) de embeddings float32.
                     n_samples deve ser >= target_dim.
        """
        n_samples, n_dims = vectors.shape
        if self._target_dim > n_dims:
            raise ValueError(
                f"PCA: target_dim ({self._target_dim}) não pode ser maior que "
                f"a dimensão de entrada ({n_dims})."
            )
        if n_samples < self._target_dim:
            raise ValueError(
                f"PCA requer n_samples ({n_samples}) >= target_dim ({self._target_dim})."
            )
        self._pca = PCA(n_components=self._target_dim, svd_solver="full")
        self._pca.fit(vectors.astype(np.float32))

    def transform(self, vectors: np.ndarray) -> np.ndarray:
        """Projeta vetores no espaço de componentes principais.

        Raises:
            RuntimeError: se chamado antes de `fit`.
        """
        if self._pca is None:
            raise RuntimeError("PcaCompressor.fit() deve ser chamado antes de transform().")

        compressed = self._pca.transform(vectors.astype(np.float32)).astype(np.float32)

        return cast(
            NDArray[np.float32],
            compressed,
        )
