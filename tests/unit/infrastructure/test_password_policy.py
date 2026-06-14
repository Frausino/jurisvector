"""Testes unit do NistPasswordPolicyValidator (NIST SP 800-63B).

Estrutura:
- Gate de comprimento (rejeita curtas) testado isoladamente.
- Blocklist (rejeita senhas vazadas LONGAS) testada separadamente, com
  senhas que JÁ passam no gate de comprimento.
- owner_identifier testado por chamada (não como estado do validator).
"""

from __future__ import annotations

import pytest

from docuvector.domain.exceptions import ValidationError
from docuvector.infrastructure.security.nist_password_policy_validator import (
    NistPasswordPolicyValidator,
)


@pytest.fixture
def validator() -> NistPasswordPolicyValidator:
    return NistPasswordPolicyValidator()


# =============================================================
# Gate de comprimento
# =============================================================
@pytest.mark.unit
def test_accepts_password_with_exact_minimum_length(
    validator: NistPasswordPolicyValidator,
) -> None:
    validator.validate("ab" * 6)  # 12 chars, fora da blocklist


@pytest.mark.unit
def test_rejects_password_shorter_than_minimum(
    validator: NistPasswordPolicyValidator,
) -> None:
    with pytest.raises(ValidationError, match="12 caracteres"):
        validator.validate("curtinha")


@pytest.mark.unit
@pytest.mark.parametrize(
    "short_common_password",
    ["password123", "qwerty123", "admin123", "brasil2026"],
)
def test_short_common_passwords_rejected_by_length_gate(
    validator: NistPasswordPolicyValidator,
    short_common_password: str,
) -> None:
    """Senhas vazadas curtas batem no gate de comprimento, não na blocklist."""
    with pytest.raises(ValidationError, match="12 caracteres"):
        validator.validate(short_common_password)


@pytest.mark.unit
def test_rejects_password_exceeding_max_length(
    validator: NistPasswordPolicyValidator,
) -> None:
    with pytest.raises(ValidationError, match="exceder"):
        validator.validate("x" * 200)


@pytest.mark.unit
def test_rejects_none_password(validator: NistPasswordPolicyValidator) -> None:
    with pytest.raises(ValidationError, match="obrigatória"):
        validator.validate(None)


# =============================================================
# Blocklist (senhas vazadas com >= 12 chars)
# =============================================================
@pytest.mark.unit
@pytest.mark.parametrize(
    "common_password",
    [
        "docuvector123",
        "docuvector1234",
        "password1234",
        "qwerty1234567",
        "iloveyou1234",
        "brasil2026brasil",
    ],
)
def test_rejects_common_passwords_that_pass_length_gate(
    validator: NistPasswordPolicyValidator,
    common_password: str,
) -> None:
    """Senha >= 12 chars presente na blocklist é rejeitada por 'vazadas'."""
    with pytest.raises(ValidationError, match="vazadas"):
        validator.validate(common_password)


@pytest.mark.unit
def test_blocklist_is_case_insensitive(
    validator: NistPasswordPolicyValidator,
) -> None:
    """`DocuVector123` casa com `docuvector123` na lista."""
    with pytest.raises(ValidationError, match="vazadas"):
        validator.validate("DocuVector123")


@pytest.mark.unit
def test_accepts_uncommon_long_password(
    validator: NistPasswordPolicyValidator,
) -> None:
    """Senha longa fora da lista de vazadas passa sem exigir complexidade."""
    validator.validate("memoriaprodigiosa")  # 17 chars, só letras minúsculas


@pytest.mark.unit
def test_accepts_passphrase_style(
    validator: NistPasswordPolicyValidator,
) -> None:
    """Passphrases (recomendação NIST) passam sem fricção."""
    validator.validate("o gato dorme no telhado azul")


# =============================================================
# owner_identifier (passado por chamada — defesa REAL no fluxo)
# =============================================================
@pytest.mark.unit
def test_rejects_password_containing_email_local_part(
    validator: NistPasswordPolicyValidator,
) -> None:
    with pytest.raises(ValidationError, match="identificador"):
        validator.validate(
            "alicedolimasilva",
            owner_identifier="alice@example.com",
        )


@pytest.mark.unit
def test_rejects_email_local_part_case_insensitive(
    validator: NistPasswordPolicyValidator,
) -> None:
    with pytest.raises(ValidationError, match="identificador"):
        validator.validate(
            "ALICEPRECISAMUDAR",
            owner_identifier="alice@example.com",
        )


@pytest.mark.unit
def test_accepts_password_unrelated_to_email(
    validator: NistPasswordPolicyValidator,
) -> None:
    validator.validate(
        "senhamuitorobustadelima",
        owner_identifier="alice@example.com",
    )


@pytest.mark.unit
def test_short_local_part_is_not_checked(
    validator: NistPasswordPolicyValidator,
) -> None:
    """Email com local-part < 4 chars não é verificado (evita falsos positivos)."""
    # 'ab' tem 2 chars: não é comparado. Senha contém 'ab' mas passa.
    validator.validate("ababcdefghij", owner_identifier="ab@x.com")


@pytest.mark.unit
def test_owner_identifier_none_skips_check(
    validator: NistPasswordPolicyValidator,
) -> None:
    """Sem identifier, comparação não ocorre."""
    validator.validate("senhamuitorobusta", owner_identifier=None)
