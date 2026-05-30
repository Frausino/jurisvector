"""Testes unitários do `BcryptPasswordHasher`."""

from __future__ import annotations

import pytest

from docuvector.domain.exceptions import ValidationError
from docuvector.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher


@pytest.fixture
def hasher() -> BcryptPasswordHasher:
    """Hasher com cost reduzido para acelerar testes (4 em vez de 12).

    Redução é segura em contexto de teste: aqui validamos comportamento,
    não resistência criptográfica. Cost de produção permanece 12 em runtime.
    """
    return BcryptPasswordHasher(rounds=4)


@pytest.mark.unit
def test_hashing_a_password_returns_bcrypt_sha256_formatted_string(
    hasher: BcryptPasswordHasher,
) -> None:
    """Hash deve seguir o formato do `bcrypt_sha256`."""
    hashed = hasher.hash("ContratoFiel#2026")

    assert hashed.startswith("$bcrypt-sha256$")
    assert len(hashed) >= 59


@pytest.mark.unit
def test_correct_password_verifies_against_its_own_hash(
    hasher: BcryptPasswordHasher,
) -> None:
    """Round-trip: senha original deve verificar contra o próprio hash."""
    original_password = "ContratoFiel#2026"  # pragma: allowlist secret
    hashed = hasher.hash(original_password)

    assert hasher.verify(original_password, hashed) is True


@pytest.mark.unit
def test_wrong_password_is_rejected(hasher: BcryptPasswordHasher) -> None:
    """Senha diferente da original NÃO pode verificar contra o hash."""
    hashed = hasher.hash("ContratoFiel#2026")

    assert hasher.verify("OutraSenha456", hashed) is False


@pytest.mark.unit
def test_empty_password_raises_validation_error(hasher: BcryptPasswordHasher) -> None:
    """Hasher rejeita senha vazia."""
    with pytest.raises(ValidationError):
        hasher.hash("")


@pytest.mark.unit
def test_empty_inputs_never_verify_successfully(hasher: BcryptPasswordHasher) -> None:
    """Entradas vazias retornam False sem levantar exceção."""
    valid_hash = hasher.hash("ContratoFiel#2026")

    assert hasher.verify("", valid_hash) is False
    assert hasher.verify("ContratoFiel#2026", "") is False


@pytest.mark.unit
def test_malformed_hash_returns_false_instead_of_raising(
    hasher: BcryptPasswordHasher,
) -> None:
    """Hash malformado retorna False; evita vazar info pelo tipo de erro."""
    assert hasher.verify("qualquer_senha_123", "isto-nao-eh-um-hash") is False


@pytest.mark.unit
def test_two_hashes_of_same_password_differ_due_to_salt(
    hasher: BcryptPasswordHasher,
) -> None:
    """Cada chamada gera salt único; hashes não devem colidir."""
    first_hash = hasher.hash("ContratoFiel#2026")
    second_hash = hasher.hash("ContratoFiel#2026")

    assert first_hash != second_hash
    assert hasher.verify("ContratoFiel#2026", first_hash) is True
    assert hasher.verify("ContratoFiel#2026", second_hash) is True
