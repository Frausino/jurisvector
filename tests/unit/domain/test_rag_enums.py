"""Testes unitários dos enums do domínio.

Importam-se especificamente os enums novos da Sprint 3 (FileFormat,
DocumentStatus, EmbeddingProviderName). Os enums anteriores estão
cobertos indiretamente pelos testes que já existiam.
"""

from __future__ import annotations

import pytest

from docuvector.domain.enums import (
    DocumentStatus,
    EmbeddingProviderName,
    FileFormat,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("file_format", "expected_value"),
    [
        (FileFormat.PDF, "pdf"),
        (FileFormat.TXT, "txt"),
        (FileFormat.MD, "md"),
    ],
)
def test_file_format_values_match_serialized_form(
    file_format: FileFormat,
    expected_value: str,
) -> None:
    """Valor serializado dos enums precisa bater com migrations e Chroma."""
    assert file_format.value == expected_value


@pytest.mark.unit
def test_document_status_lifecycle_values_are_unique_and_lowercase() -> None:
    """Garante consistência de naming e ausência de duplicatas."""
    values = [member.value for member in DocumentStatus]

    assert len(values) == len(set(values)), "valores duplicados em DocumentStatus"
    assert all(value == value.lower() for value in values), "valores devem ser lowercase"
    assert "embedded" in values
    assert "failed" in values


@pytest.mark.unit
def test_embedding_provider_name_lists_supported_backends() -> None:
    """O enum espelha exatamente os provedores que a infraestrutura suporta."""
    supported = {member.value for member in EmbeddingProviderName}

    assert supported == {"openai", "sentence_transformers"}


@pytest.mark.unit
def test_enums_value_attribute_is_the_canonical_serialized_form() -> None:
    """`.value` é a forma persistida no banco e usada em chamadas externas.

    Não comparamos `FileFormat.PDF == "pdf"` diretamente: apesar do
    `str, Enum` permitir isso em runtime, mypy strict rejeita por
    `comparison-overlap`. Acessar `.value` deixa a intenção explícita.
    """
    assert FileFormat.PDF.value == "pdf"
    assert DocumentStatus.EMBEDDED.value == "embedded"
    assert EmbeddingProviderName.OPENAI.value == "openai"
