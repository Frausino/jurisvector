"""Compressor de embeddings via quantização Int8.

Trade-off: sem redução de dimensão (compressed_dim == original_dim), mas
4x menos bytes (float32 = 4 bytes → int8 = 1 byte). Perda semântica mínima
porque a estrutura relativa entre vetores é preservada quase integralmente.

Stateless: `fit` é no-op; `transform` pode ser chamado sem fit anterior.
Isso simplifica o pipeline: não há estado a carregar ou serializar.

Implementação:
- Escala cada vetor individualmente pelo seu valor absoluto máximo.
- Fórmula: q = clip(round(v / max_abs * 127), -127, 127).astype(int8)
- `max_abs` por vetor (não global) evita distorção causada por outliers.
- bytes_per_element = 1.0.

Limitação intencional (Sprint 4A):
  O `max_abs` não é persistido após o transform. Isso torna a operação
  não-reversível: não há como desquantizar o vetor sem o fator de escala.
  Para Sprint 4A apenas medimos retenção semântica e bytes economizados.
  Suporte a reconstrução (desquantização) fica como evolução futura.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import NDArray

from docuvector.domain.enums import CompressionMethod


class Int8Compressor:
    """Implementa `Compressor` via quantização int8 por vetor."""

    _BYTES_PER_ELEMENT: float = 1.0  # int8

    def __init__(self, target_dim: int | None = None) -> None:
        # target_dim é ignorado: Int8 não reduz dimensão.
        # Aceita o parâmetro para manter interface uniforme com os outros.
        self._target_dim: int | None = target_dim

    @property
    def method_name(self) -> CompressionMethod:
        return CompressionMethod.INT8

    @property
    def target_dim(self) -> int | None:
        """Retorna a dimensão após compressão, ou None se fit/transform
        ainda não foram chamados. Int8 não reduz dimensão."""
        return self._target_dim

    @property
    def bytes_per_element(self) -> float:
        return self._BYTES_PER_ELEMENT

    def fit(self, vectors: np.ndarray) -> None:
        """Inicializa target_dim a partir da dimensão de entrada.

        Int8 não aprende parâmetros do dado (sem SVD, sem projeção).
        A quantização é determinística e aplicada inteiramente em transform().
        Não há estado a serializar ou reutilizar entre chamadas.
        """
        self._target_dim = vectors.shape[1]

    def transform(self, vectors: np.ndarray) -> np.ndarray:
        """Quantiza vetores float32 para int8 e atualiza target_dim.

        Pode ser chamado sem fit() anterior — target_dim é determinado
        pela dimensão de entrada nesta chamada.

        Sem reconstrução reversível (Sprint 4A): o fator max_abs por
        vetor não é persistido. Desquantizar exigiria armazenar os
        fatores de escala — fora do escopo desta sprint.

        Args:
            vectors: Matriz (n_samples, n_dims) de embeddings float32.

        Returns:
            Matriz (n_samples, n_dims) em dtype int8, valores em [-127, 127].
        """
        float_vectors = vectors.astype(np.float32)

        # max_abs por linha (keepdims para broadcast).
        # Adiciona epsilon para evitar divisão por zero em vetores nulos.
        max_abs = np.abs(float_vectors).max(axis=1, keepdims=True) + 1e-8

        scaled = float_vectors / max_abs * 127.0
        quantized = np.clip(np.round(scaled), -127, 127).astype(np.int8)

        self._target_dim = quantized.shape[1]
        return cast(
            NDArray[np.int8],
            quantized,
        )
