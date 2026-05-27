"""Implementação SQLAlchemy do `UserRepository`."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole
from docuvector.infrastructure.persistence.models import UserModel


class SqlAlchemyUserRepository:
    """Repositório de usuários sobre PostgreSQL.

    Traduz entre `UserModel` (ORM) e `User` (entidade de domínio) para
    manter o domínio livre de qualquer dependência de SQLAlchemy.
    Satisfaz estruturalmente `domain.interfaces.UserRepository`.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_email(self, email: str) -> User | None:
        statement = select(UserModel).where(UserModel.email == email.lower().strip())
        record = self._session.scalars(statement).one_or_none()
        return None if record is None else _to_entity(record)

    def find_by_id(self, user_id: UUID) -> User | None:
        record = self._session.get(UserModel, user_id)
        return None if record is None else _to_entity(record)

    def save(self, user: User) -> User:
        existing = self._session.get(UserModel, user.id)
        if existing is None:
            record = _to_model(user)
            self._session.add(record)
        else:
            existing.email = user.email
            existing.password_hash = user.password_hash
            existing.role = user.role
            existing.is_active = user.is_active
            record = existing
        self._session.flush()
        return _to_entity(record)


def _to_entity(record: UserModel) -> User:
    """Converte modelo ORM para entidade pura de domínio."""
    return User(
        id=record.id,
        email=record.email,
        password_hash=record.password_hash,
        role=UserRole(record.role),
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_model(user: User) -> UserModel:
    """Converte entidade de domínio para modelo ORM (insert)."""
    return UserModel(
        id=user.id,
        email=user.email,
        password_hash=user.password_hash,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
