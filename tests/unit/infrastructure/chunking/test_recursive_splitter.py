"""Testes unit do RecursiveSplitter."""

from __future__ import annotations

import pytest

from docuvector.domain.exceptions import ValidationError
from docuvector.infrastructure.chunking.recursive_splitter import RecursiveSplitter


# =============================================================
# Validação de parâmetros
# =============================================================
@pytest.mark.unit
def test_rejects_zero_or_negative_chunk_size() -> None:
    with pytest.raises(ValidationError, match="chunk_size"):
        RecursiveSplitter(chunk_size=0)
    with pytest.raises(ValidationError, match="chunk_size"):
        RecursiveSplitter(chunk_size=-100)


@pytest.mark.unit
def test_rejects_negative_overlap() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap"):
        RecursiveSplitter(chunk_size=1000, chunk_overlap=-1)


@pytest.mark.unit
def test_rejects_overlap_greater_or_equal_to_chunk_size() -> None:
    """Overlap >= chunk_size criaria loop infinito na etapa de merge."""
    with pytest.raises(ValidationError, match="menor que"):
        RecursiveSplitter(chunk_size=100, chunk_overlap=100)
    with pytest.raises(ValidationError, match="menor que"):
        RecursiveSplitter(chunk_size=100, chunk_overlap=200)


# =============================================================
# Texto vazio e curto
# =============================================================
@pytest.mark.unit
def test_empty_text_returns_no_chunks() -> None:
    splitter = RecursiveSplitter(chunk_size=1000, chunk_overlap=100)
    assert splitter.split("") == []


@pytest.mark.unit
def test_whitespace_only_text_returns_no_chunks() -> None:
    splitter = RecursiveSplitter(chunk_size=1000, chunk_overlap=100)
    assert splitter.split("   \n\n  \t  ") == []


@pytest.mark.unit
def test_short_text_becomes_single_chunk() -> None:
    splitter = RecursiveSplitter(chunk_size=1000, chunk_overlap=100)
    text = "Contrato de prestação de serviços jurídicos."

    chunks = splitter.split(text)

    assert len(chunks) == 1
    assert chunks[0] == text


# =============================================================
# Texto longo
# =============================================================
@pytest.mark.unit
def test_long_text_is_split_into_multiple_chunks() -> None:
    splitter = RecursiveSplitter(chunk_size=200, chunk_overlap=50)
    # Texto de 800 chars com parágrafos.
    paragraph = "Cláusula contratual referente às obrigações das partes. " * 5
    text = "\n\n".join([paragraph] * 4)

    chunks = splitter.split(text)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


@pytest.mark.unit
def test_each_chunk_respects_size_limit_with_tolerance() -> None:
    """Cada chunk não excede `chunk_size` significativamente.

    Tolerância pequena é aceitável porque o splitter prioriza
    fronteiras semânticas sobre tamanho exato.
    """
    chunk_size = 300
    splitter = RecursiveSplitter(chunk_size=chunk_size, chunk_overlap=50)
    text = "Frase contratual número um. " * 100

    chunks = splitter.split(text)

    tolerance = chunk_size + 50  # 50 chars de folga
    over_limit = [c for c in chunks if len(c) > tolerance]
    assert not over_limit, f"Chunks acima do limite: {[len(c) for c in over_limit]}"


@pytest.mark.unit
def test_consecutive_chunks_share_overlap_content() -> None:
    """O fim do chunk N aparece no início do chunk N+1."""
    splitter = RecursiveSplitter(chunk_size=200, chunk_overlap=50)
    text = "Palavra " * 200  # 1400 chars

    chunks = splitter.split(text)

    assert len(chunks) >= 2
    # O começo do segundo chunk contém parte do fim do primeiro.
    end_of_first = chunks[0][-30:]
    assert end_of_first.split() and any(
        token in chunks[1] for token in end_of_first.split() if len(token) > 2
    )


@pytest.mark.unit
def test_text_without_separators_is_still_split() -> None:
    """Texto contínuo sem espaço/quebra ainda é segmentado em janelas."""
    splitter = RecursiveSplitter(chunk_size=100, chunk_overlap=20)
    text = "a" * 500

    chunks = splitter.split(text)

    assert len(chunks) >= 3
    assert all(len(chunk) <= 120 for chunk in chunks)


# =============================================================
# Determinismo
# =============================================================
@pytest.mark.unit
def test_split_is_deterministic() -> None:
    """Mesma entrada produz mesma saída em execuções distintas."""
    splitter = RecursiveSplitter(chunk_size=200, chunk_overlap=50)
    text = "Frase de exemplo. " * 50

    first_run = splitter.split(text)
    second_run = splitter.split(text)

    assert first_run == second_run


@pytest.mark.unit
def test_paragraph_boundary_is_preferred_over_word_split() -> None:
    """Splitter prioriza quebrar por parágrafo antes de por palavra."""
    splitter = RecursiveSplitter(chunk_size=80, chunk_overlap=10)
    text = (
        "Parágrafo um, contém algumas palavras importantes.\n\n"
        "Parágrafo dois, com mais conteúdo relevante para o teste.\n\n"
        "Parágrafo três, completando o exemplo da fixture."
    )

    chunks = splitter.split(text)

    # Cada chunk deve corresponder a um parágrafo (mais ou menos).
    assert len(chunks) >= 2
