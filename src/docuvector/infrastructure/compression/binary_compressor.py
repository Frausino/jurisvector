"""Compressor de embeddings via binarização por limiarização.

Trade-off: redução teórica de 32x em bytes (float32 = 32 bits → 1 bit),
maior perda semântica entre os 4 compressores. Útil para filtros aproximados
e pré-seleção rápida em pipelines de retrieval em dois estágios.

Stateless: `fit` é no-op. `transform` pode ser chamado sem fit anterior.

Implementação:
- Limiar: v > 0 → 1, v ≤ 0 → 0.
- Saída em uint8 (não packbits) para manter interface ndarray uniforme.
  O ratio teórico de 32x é preservado como metadata; o armazenamento
  efetivo com packbits é responsabilidade da camada de persistência futura.
- bytes_per_element = 0.125 (1/8 de byte = 1 bit teórico).

ATENÇÃO — economia teórica vs real:
  `space_savings_pct` e `ratio_bytes` calculados com bytes_per_element=0.125
  assumem que os vetores serão empacotados com packbits na persistência.
  A saída atual (uint8, 1 byte/elem) NÃO reflete essa economia em disco.
  Ao apresentar os números para a banca, deixar explícito:
  "economia teórica assumindo packbits". A implementação do packbits
  fica como evolução futura, fora do escopo da Sprint 4A.

Nota sobre o ratio teórico:
  Se n_dims = 384, cada vetor float32 ocupa 384 x 4 = 1536 bytes.
  Com binarização e packbits, ocuparia 384 / 8 = 48 bytes.
  Sem packbits (uint8), ocupa 384 bytes — mas o bytes_per_element=0.125
  ainda é usado para calcular a economia potencial, que é o número que
  importa para a banca e para estimativas de custo em Pinecone/Qdrant.
"""

from __future__ import annotations

import numpy as np

from docuvector.domain.enums import CompressionMethod


class BinaryCompressor:
    """Implementa `Compressor` via binarização por limiar zero."""

    _BYTES_PER_ELEMENT: float = 0.125  # 1 bit teórico = 1/8 de byte

    def __init__(self, target_dim: int | None = None) -> None:
        # target_dim é ignorado: Binary não reduz dimensão.
        self._target_dim: int | None = target_dim

    @property
    def method_name(self) -> CompressionMethod:
        return CompressionMethod.BINARY

    @property
    def target_dim(self) -> int | None:
        """Retorna a dimensão após compressão, ou None se fit/transform
        ainda não foram chamados. Binary não reduz dimensão."""
        return self._target_dim

    @property
    def bytes_per_element(self) -> float:
        return self._BYTES_PER_ELEMENT

    def fit(self, vectors: np.ndarray) -> None:
        """Inicializa target_dim a partir da dimensão de entrada.

        Binary não aprende parâmetros: o limiar é sempre zero,
        determinístico e independente dos dados. Não há estado a
        serializar ou reutilizar entre chamadas.
        """
        self._target_dim = vectors.shape[1]

    def transform(self, vectors: np.ndarray) -> np.ndarray:
        """Binariza vetores pelo limiar zero e atualiza target_dim.

        Pode ser chamado sem fit() anterior — target_dim é determinado
        pela dimensão de entrada nesta chamada.

        Saída em uint8 (1 byte/elem) para manter interface ndarray
        uniforme. A economia de 32x é teórica (assumindo packbits na
        persistência) — ver bytes_per_element=0.125 e nota no módulo.

        Args:
            vectors: Matriz (n_samples, n_dims) de embeddings float32.

        Returns:
            Matriz (n_samples, n_dims) em dtype uint8, valores 0 ou 1.
        """
        binarized = (vectors > 0).astype(np.uint8)
        self._target_dim = binarized.shape[1]
        return binarized
