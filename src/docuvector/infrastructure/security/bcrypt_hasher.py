"""Implementação de hashing de senha com bcrypt (via passlib).

Decisão: bcrypt com cost 12 atende OWASP Password Storage Cheat Sheet
para 2026. Argon2id seria superior em hardware moderno, mas bcrypt
ainda é o padrão de fato e tem suporte nativo do passlib sem libs C
adicionais.
"""

from __future__ import annotations

from passlib.context import CryptContext

from docuvector.domain.exceptions import ValidationError

_MIN_PASSWORD_LENGTH = 8
_DEFAULT_BCRYPT_ROUNDS = 12


class BcryptPasswordHasher:
    """Hashing one-way de senhas com bcrypt e cost factor 12.

    Satisfaz estruturalmente `domain.interfaces.PasswordHasher`.
    """

    def __init__(self, rounds: int = _DEFAULT_BCRYPT_ROUNDS) -> None:
        self._crypt_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=rounds,
        )

    def hash(self, plain_password: str) -> str:
        """Retorna hash bcrypt no formato `$2b$<rounds>$<salt><hash>`.

        Levanta `ValidationError` se a senha for vazia ou abaixo do mínimo.
        """
        if not plain_password or len(plain_password) < _MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"A senha deve ter no mínimo {_MIN_PASSWORD_LENGTH} caracteres.",
            )
        return self._crypt_context.hash(plain_password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica em tempo constante se a senha em claro confere com o hash.

        Retorna False (não levanta) em qualquer caso de falha, inclusive
        hash malformado. Evita vazar informação por tipo de erro.
        """
        if not plain_password or not hashed_password:
            return False
        try:
            return self._crypt_context.verify(plain_password, hashed_password)
        except (ValueError, TypeError):
            return False
