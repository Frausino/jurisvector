"""Contrato de repositório de usuários."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from docuvector.domain.entities import User


class UserRepository(Protocol):
    """Persistência de entidades User.

    Implementação concreta (SQLAlchemy) vive em
    `infrastructure/persistence/user_repository_impl.py`.
    """

    def find_by_email(self, email: str) -> User | None:
        """Retorna o usuário com o e-mail informado, ou None se inexistente."""
        ...

    def find_by_id(self, user_id: UUID) -> User | None:
        """Retorna o usuário com o id informado, ou None se inexistente."""
        ...

    def save(self, user: User) -> User:
        """Persiste o usuário (insert ou update); retorna a versão persistida."""
        ...
