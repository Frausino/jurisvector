"""Resultado de um benchmark de compressão de embeddings.

Design:

- **Um único dataclass**, sem `CompressionResult` separado. Tudo o que o use
  case produz, o repositório persiste e o endpoint serializa vem daqui.

- **`space_savings_pct` calculado em `__post_init__`** a partir de
  `original_dim`, `compressed_dim` e `bytes_per_element`. Isso garante que
  o endpoint, o dashboard e os testes sempre leiam o mesmo valor derivado,
  sem recálculo espalhado pelo código.

- **`semantic_retention`** é a correlação de Pearson entre as matrizes de
  similaridade coseno antes e depois da compressão (não entre normas). Mede
  preservação da estrutura relativa entre chunks — o que importa para RAG.

- Frozen + slots: domínio imutável, sem efeitos colaterais.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docuvector.domain.enums import CompressionMethod

# Bytes que um float32 ocupa (todos os embeddings originais são float32).
_FLOAT32_BYTES: float = 4.0


@dataclass(frozen=True, slots=True)
class CompressionMetrics:
    """Métricas completas de um compressor aplicado a um conjunto de vetores.

    Campos obrigatórios calculados pelo `CompressionBenchmarkUseCase`.
    `space_savings_pct` e `ratio_bytes` são derivados e calculados aqui
    para evitar duplicação.

    Exemplo de interpretação:
        original_dim=384, compressed_dim=192, bytes_per_element=4.0
        → ratio_bytes=2.0  (ocupa a metade)
        → space_savings_pct=50.0  (50% de economia)

        original_dim=384, compressed_dim=384, bytes_per_element=1.0
        → ratio_bytes=4.0  (Int8, 4x menos bytes)
        → space_savings_pct=75.0
    """

    method: CompressionMethod
    original_dim: int
    compressed_dim: int
    bytes_per_element: float  # 4.0=float32, 1.0=int8, 0.125=binary
    fit_time_ms: int
    transform_time_ms: int
    semantic_retention: float  # Pearson de cosine_sim_matrix [0.0, 1.0]
    n_vectors: int  # quantos chunks foram usados no benchmark

    # Campos derivados: calculados em __post_init__ e imutáveis após isso.
    ratio_bytes: float = field(init=False)
    space_savings_pct: float = field(init=False)

    def __post_init__(self) -> None:
        """Calcula os campos derivados a partir dos valores fornecidos.

        Usa object.__setattr__ porque o dataclass é frozen=True.
        """
        ratio = (self.original_dim * _FLOAT32_BYTES) / (
            self.compressed_dim * self.bytes_per_element
        )

        savings = (1.0 - 1.0 / ratio) * 100.0

        # frozen=True exige contornar a proteção de imutabilidade aqui,
        # apenas neste ponto de inicialização. É o padrão documentado pelo
        # Python para campos derivados em dataclasses frozen.
        object.__setattr__(self, "ratio_bytes", ratio)
        object.__setattr__(self, "space_savings_pct", savings)

    def is_lossless_threshold(self, min_retention: float = 0.95) -> bool:
        """Retorna True se a retenção semântica está acima do limiar."""
        return self.semantic_retention >= min_retention

    def storage_bytes(self, n_chunks: int) -> int:
        """Bytes ocupados por `n_chunks` vetores comprimidos com este método."""
        return int(n_chunks * self.compressed_dim * self.bytes_per_element)

    def original_storage_bytes(self, n_chunks: int) -> int:
        """Bytes ocupados pelos vetores originais (float32)."""
        return int(n_chunks * self.original_dim * _FLOAT32_BYTES)
