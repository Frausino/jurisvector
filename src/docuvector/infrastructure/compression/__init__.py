"""Compressores concretos de embeddings."""

from docuvector.infrastructure.compression.binary_compressor import BinaryCompressor
from docuvector.infrastructure.compression.int8_compressor import Int8Compressor
from docuvector.infrastructure.compression.pca_compressor import PcaCompressor
from docuvector.infrastructure.compression.random_projection_compressor import (
    RandomProjectionCompressor,
)

__all__ = [
    "BinaryCompressor",
    "Int8Compressor",
    "PcaCompressor",
    "RandomProjectionCompressor",
]


def build_all_compressors(
    target_dim: int,
) -> list[PcaCompressor | RandomProjectionCompressor | Int8Compressor | BinaryCompressor]:
    """Constrói uma instância de cada compressor com o mesmo target_dim.

    Convenção do benchmark: Int8 e Binary ignoram target_dim internamente
    (sem redução de dimensão), mas aceitam o parâmetro por interface uniforme.
    """
    return [
        PcaCompressor(target_dim=target_dim),
        RandomProjectionCompressor(target_dim=target_dim),
        Int8Compressor(target_dim=target_dim),
        BinaryCompressor(target_dim=target_dim),
    ]
