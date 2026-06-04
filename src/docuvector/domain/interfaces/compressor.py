"""Interface (Protocol) para compressores de embeddings.

Design:

- **`fit` e `transform` separados** porque PCA e RandomProjection precisam
  de fit em batch sobre a matriz completa antes de transformar. Int8 e Binary
  são stateless e implementam `fit` como no-op. Interface uniforme: o
  `CompressionBenchmarkUseCase` chama sempre `fit → transform`, sem `if`.

- **`bytes_per_element` como property** permite que o use case calcule
  `ratio_bytes` e `space_savings_pct` via polimorfismo, sem switch/if sobre
  o tipo de compressor:

      ratio = (original_dim * 4.0) / (compressed_dim * compressor.bytes_per_element)

  Cada compressor declara seu próprio dtype de saída:
      PCA, RandomProjection → float32 → 4.0
      Int8                  → int8    → 1.0
      Binary                → 1 bit   → 0.125  (teórico; saída é uint8 por praticidade)

- **Domínio puro**: zero imports de sklearn, scipy ou numpy neste módulo.
  O Protocol só descreve a interface; as implementações ficam em
  `infrastructure/compression/`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

    from docuvector.domain.enums import CompressionMethod


@runtime_checkable
class Compressor(Protocol):
    """Contrato para qualquer compressor de vetores de embedding.

    Implementações concretas: PcaCompressor, RandomProjectionCompressor,
    Int8Compressor, BinaryCompressor.
    """

    @property
    def method_name(self) -> CompressionMethod:
        """Identificador canônico do método."""
        ...

    @property
    def target_dim(self) -> int | None:
        """Dimensão alvo após compressão.

        Para compressores stateful (PCA, RandomProjection), retorna o valor
        passado no construtor.
        Para compressores stateless (Int8, Binary), retorna None até que
        fit() ou transform() sejam chamados — a dimensão é determinada
        pela entrada, não pelo construtor.
        """
        ...

    @property
    def bytes_per_element(self) -> float:
        """Bytes que cada elemento ocupa no vetor comprimido.

        - float32 (PCA, RandomProjection): 4.0
        - int8: 1.0
        - binary (teórico): 0.125  (1 bit = 1/8 byte)
        """
        ...

    def fit(self, vectors: np.ndarray) -> None:
        """Ajusta o compressor à distribuição dos vetores de entrada.

        Para compressores stateless (Int8, Binary), este método é no-op mas
        deve ser chamado mesmo assim para manter a interface uniforme.

        Args:
            vectors: Matriz (n_samples, n_dims) de embeddings float32.
        """
        ...

    def transform(self, vectors: np.ndarray) -> np.ndarray:
        """Comprime os vetores usando os parâmetros ajustados em `fit`.

        Levanta RuntimeError se chamado antes de `fit` em compressores
        stateful (PCA, RandomProjection).

        Args:
            vectors: Matriz (n_samples, n_dims) de embeddings float32.

        Returns:
            Matriz (n_samples, target_dim) no dtype correspondente ao compressor.
        """
        ...
