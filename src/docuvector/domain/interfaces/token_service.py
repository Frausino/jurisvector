"""Contrato de serviço de tokens de sessão."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Claims extraídas de um token verificado.

    O domínio expressa o que precisa saber sobre uma sessão sem
    depender de JWT, OAuth ou qualquer formato wire específico.
    """

    user_id: UUID
    email: str
    role: UserRole
    expires_at: datetime


class TokenService(Protocol):
    """Emissão e verificação de tokens de autenticação."""

    def issue(self, user: User) -> str:
        """Gera um token assinado representando a sessão do usuário."""
        ...

    def verify(self, raw_token: str) -> TokenPayload:
        """Valida o token e retorna os claims.

        Levanta `AuthenticationError` se o token for inválido, expirado,
        adulterado ou em formato desconhecido.
        """
        ...
