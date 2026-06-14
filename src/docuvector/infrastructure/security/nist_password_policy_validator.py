"""Implementação de `PasswordPolicyValidator` seguindo NIST SP 800-63B (2024).

Diretrizes aplicadas:

1.  **Comprimento mínimo de 12 caracteres** (configurável via Settings).
2.  **Sem regras de complexidade artificial** (NIST 5.1.1.2).
3.  **Bloqueio de senhas vazadas** via lista local de comprimento >= min_length.
4.  **Bloqueio de senhas iguais ao identificador do usuário** (passado
    por chamada; o validator é stateless e singleton por processo).
5.  **Sem expiração compulsória** (NIST 5.1.1.2).

A lista de senhas comuns carrega uma vez por processo (`@lru_cache`)
e fica como `frozenset` para lookup O(1).
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from docuvector.domain.exceptions import ValidationError

_DEFAULT_MIN_LENGTH = 12
_MAX_LENGTH = 128
_NIST_ABSOLUTE_MIN_LENGTH = 8  # NIST SP 800-63B 5.1.1.2: floor absoluto
_COMMON_PASSWORDS_FILENAME = "common_passwords.txt"
_MIN_IDENTIFIER_LOCAL_PART_TO_CHECK = 4


@lru_cache(maxsize=1)
def _load_common_passwords() -> frozenset[str]:
    """Carrega a lista de senhas vazadas embarcada no pacote."""
    common_passwords_path = Path(__file__).parent / _COMMON_PASSWORDS_FILENAME
    if not common_passwords_path.exists():
        return frozenset()

    with common_passwords_path.open("r", encoding="utf-8") as common_passwords_file:
        return frozenset(
            line.strip().lower()
            for line in common_passwords_file
            if line.strip() and not line.startswith("#")
        )


class NistPasswordPolicyValidator:
    """Política de senha alinhada a NIST SP 800-63B (Rev. 4, 2024)."""

    def __init__(
        self,
        min_length: int = _DEFAULT_MIN_LENGTH,
        max_length: int = _MAX_LENGTH,
    ) -> None:
        if min_length < _NIST_ABSOLUTE_MIN_LENGTH:
            raise ValidationError(
                f"`min_length` não pode ser menor que {_NIST_ABSOLUTE_MIN_LENGTH} (NIST 5.1.1.2)."
            )
        self._min_length = min_length
        self._max_length = max_length

    def validate(self, plain_password: str | None, owner_identifier: str | None = None) -> None:
        """Valida a senha; levanta `ValidationError` com motivo explícito."""
        if not plain_password or not plain_password.strip():
            raise ValidationError("Senha é obrigatória e não pode conter apenas espaços.")

        # Normaliza a entrada para garantir consistência em caracteres Unicode (acentos/emojis)
        normalized_password = unicodedata.normalize("NFKC", plain_password)

        self._enforce_length_bounds(normalized_password)
        self._reject_if_in_common_passwords(normalized_password)
        self._reject_if_matches_identifier(normalized_password, owner_identifier)

    def _enforce_length_bounds(self, plain_password: str) -> None:
        password_length = len(plain_password)
        if password_length < self._min_length:
            raise ValidationError(f"Senha deve ter pelo menos {self._min_length} caracteres.")
        if password_length > self._max_length:
            raise ValidationError(f"Senha não pode exceder {self._max_length} caracteres.")

    @staticmethod
    def _reject_if_in_common_passwords(plain_password: str) -> None:
        common_passwords = _load_common_passwords()
        if plain_password.lower() in common_passwords:
            raise ValidationError(
                "Esta senha aparece em listas públicas de senhas vazadas. "
                "Escolha outra mais singular."
            )

    @staticmethod
    def _reject_if_matches_identifier(
        plain_password: str,
        owner_identifier: str | None,
    ) -> None:
        """Rejeita se a senha contém o identificador do usuário.

        Para emails, considera o local-part (parte antes do '@'). Para
        identificadores arbitrários, compara o valor inteiro. Identificadores
        com menos de 4 chars são ignorados para evitar falsos positivos.
        """
        if owner_identifier is None:
            return

        comparable_token = owner_identifier.split("@", maxsplit=1)[0].lower().strip()
        if len(comparable_token) < _MIN_IDENTIFIER_LOCAL_PART_TO_CHECK:
            return

        if comparable_token in plain_password.lower():
            raise ValidationError("Senha não pode conter o seu identificador de usuário.")