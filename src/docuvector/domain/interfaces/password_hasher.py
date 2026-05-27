"""Contrato de serviço de hash de senha."""

from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    """Hashing one-way de senhas com salt.

    Implementação concreta usa bcrypt (ver
    `infrastructure/security/bcrypt_hasher.py`).
    O domínio não conhece o algoritmo: poderia ser argon2id ou scrypt.
    """

    def hash(self, plain_password: str) -> str:
        """Retorna o hash da senha em formato auto-contido (algoritmo + salt + hash)."""
        ...

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica em tempo constante se a senha em claro confere com o hash."""
        ...
