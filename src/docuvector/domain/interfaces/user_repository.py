"""Contrato de repositório de usuários."""

from __future__ import annotations

from collections.abc import Sequence
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

    def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[User]:
        """Lista usuários ordenados por data de criação desc (admin only).

        Paginação por `limit`/`offset` mantém o contrato simples e
        suficiente para a Sprint 2. Cursor-based fica para sprint
        futura se a base crescer.
        """
        ...

    def count_all(self) -> int:
        """Quantidade total de usuários (para metadados de paginação)."""
        ...

    def delete_by_id(self, user_id: UUID) -> bool:
        """Remove o usuário por id; devolve True se removeu, False se inexistente.

        Documentos do usuário caem por CASCADE (FK em documents.owner_id).
        Audit logs sobrevivem com user_id=NULL (FK ON DELETE SET NULL).
        """
        ...
