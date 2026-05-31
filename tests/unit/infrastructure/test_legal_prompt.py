"""Testes unit do template de prompt jurídico."""

from __future__ import annotations

from uuid import uuid4

import pytest

from docuvector.application.prompts.legal_prompt import (
    build_user_prompt,
    get_system_prompt,
)
from docuvector.domain.entities import RetrievedChunk


def _make_chunk(text: str, filename: str = "contrato.pdf", index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_filename=filename,
        text=text,
        similarity=0.9,
        chunk_index=index,
    )


# =============================================================
# System prompt
# =============================================================
@pytest.mark.unit
def test_system_prompt_demands_portuguese_response() -> None:
    prompt = get_system_prompt()
    assert "português" in prompt.casefold()


@pytest.mark.unit
def test_system_prompt_demands_inline_citations() -> None:
    prompt = get_system_prompt()
    assert "[1]" in prompt and "[2]" in prompt


@pytest.mark.unit
def test_system_prompt_defines_abstention_phrase() -> None:
    """Frase exata que o AnswerUseCase usa para detectar grounded=False."""
    prompt = get_system_prompt()
    assert "Não tenho contexto suficiente" in prompt


@pytest.mark.unit
def test_system_prompt_forbids_legal_advice() -> None:
    prompt = get_system_prompt()
    assert "aconselhamento" in prompt.casefold()


# =============================================================
# User prompt: com chunks
# =============================================================
@pytest.mark.unit
def test_build_user_prompt_numbers_chunks_starting_at_one() -> None:
    chunks = [
        _make_chunk("primeiro trecho", filename="a.pdf"),
        _make_chunk("segundo trecho", filename="b.pdf", index=2),
    ]

    prompt = build_user_prompt(query="qual a cláusula?", retrieved_chunks=chunks)

    assert "[1]" in prompt
    assert "[2]" in prompt
    assert "primeiro trecho" in prompt
    assert "segundo trecho" in prompt


@pytest.mark.unit
def test_build_user_prompt_includes_document_filenames() -> None:
    chunks = [_make_chunk("trecho de contrato", filename="contrato_X.pdf")]

    prompt = build_user_prompt(query="pergunta", retrieved_chunks=chunks)

    assert "contrato_X.pdf" in prompt


@pytest.mark.unit
def test_build_user_prompt_translates_chunk_index_to_human_number() -> None:
    """chunk_index=0 vira 'trecho 1' (mais legível para advogado leitor)."""
    chunks = [_make_chunk("conteudo", index=0)]

    prompt = build_user_prompt(query="pergunta", retrieved_chunks=chunks)

    assert "trecho 1" in prompt


@pytest.mark.unit
def test_build_user_prompt_appends_query_at_end() -> None:
    chunks = [_make_chunk("conteudo")]
    query = "Qual a cláusula de força maior?"

    prompt = build_user_prompt(query=query, retrieved_chunks=chunks)

    assert query in prompt
    # Garante ordem: contexto vem ANTES da pergunta.
    assert prompt.index("conteudo") < prompt.index(query)


# =============================================================
# User prompt: sem chunks
# =============================================================
@pytest.mark.unit
def test_build_user_prompt_with_empty_chunks_forces_abstention() -> None:
    """Sem contexto, o prompt instrui explicitamente a frase de abstenção."""
    prompt = build_user_prompt(query="pergunta sem contexto", retrieved_chunks=[])

    assert "Não tenho contexto suficiente" in prompt
    assert "pergunta sem contexto" in prompt
