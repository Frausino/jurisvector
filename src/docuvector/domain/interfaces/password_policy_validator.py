"""Contrato de validação de política de senha.

Implementação concreta vive em
`infrastructure/security/nist_password_policy_validator.py`. O método
`validate` recebe o identificador do dono como parâmetro (não como estado
do validator), eliminando a necessidade de construir uma instância nova
por request e garantindo que a defesa "senha não pode conter o email"
funcione no fluxo real, não apenas em testes.
"""

from __future__ import annotations

from typing import Protocol


class PasswordPolicyValidator(Protocol):
    """Valida se uma senha em texto plano atende à política do sistema."""

    def validate(self, plain_password: str, owner_identifier: str | None = None) -> None:
        """Valida; levanta `ValidationError` em caso de falha.

        `owner_identifier` (tipicamente o email) é comparado contra o
        conteúdo da senha. Quando None, esse check é pulado (útil em
        contextos sem identidade definida, como CLI de seed).
        """
        ...
