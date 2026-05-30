"""Implementação de hashing de senha com bcrypt (via passlib).

Decisão arquitetural CRÍTICA: o esquema é `bcrypt_sha256`, não `bcrypt`
puro. Diferença:

- `bcrypt` puro TRUNCA silenciosamente em 72 bytes. Duas senhas que
  coincidem nos primeiros 72 bytes (comum em passphrases UTF-8 com
  acentos, onde 1 char pode ser 2-4 bytes) geram o MESMO hash. Vetor
  conhecido de colisão prática.

- `bcrypt_sha256` (recomendação OWASP) aplica SHA-256 sobre a senha
  ANTES do bcrypt: a entrada para o bcrypt vira sempre 32 bytes,
  cabendo confortavelmente nos 72 do limite, e qualquer mudança na
  senha original produz hash diferente.

A constante de comprimento mínimo NÃO existe aqui: única fonte de
verdade é o `NistPasswordPolicyValidator`, executado ANTES do hash
no fluxo de use case. Duplicar criava risco de divergência.
"""

from __future__ import annotations

from passlib.context import CryptContext

from docuvector.domain.exceptions import ValidationError

_DEFAULT_BCRYPT_ROUNDS = 12


class BcryptPasswordHasher:
    """Hashing one-way de senhas com `bcrypt_sha256` (pré-hash SHA-256).

    Satisfaz estruturalmente `domain.interfaces.PasswordHasher`.
    """

    def __init__(self, rounds: int = _DEFAULT_BCRYPT_ROUNDS) -> None:
        self._crypt_context = CryptContext(
            schemes=["bcrypt_sha256"],
            deprecated="auto",
            bcrypt_sha256__rounds=rounds,
        )

    def hash(self, plain_password: str) -> str:
        """Retorna hash no formato `$bcrypt-sha256$<params>$<salt>$<hash>`.

        Levanta `ValidationError` apenas se a senha for vazia. A política
        de comprimento é responsabilidade do `PasswordPolicyValidator`
        chamado antes desta função no fluxo do use case.
        """
        if not plain_password:
            raise ValidationError("A senha não pode ser vazia.")
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
