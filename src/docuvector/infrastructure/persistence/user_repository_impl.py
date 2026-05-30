"""Implementação SQLAlchemy de `UserRepository`."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from docuvector.domain.entities import User
from docuvector.infrastructure.persistence.models import UserModel


class SqlAlchemyUserRepository:
    """Persistência de `User` usando SQLAlchemy 2.0 (ORM tipado)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -------------------------------------------------------------
    # Leitura
    # -------------------------------------------------------------
    def find_by_email(self, email: str) -> User | None:
        record = self._session.execute(
            select(UserModel).where(UserModel.email == email)
        ).scalar_one_or_none()
        return self._to_entity(record) if record is not None else None

    def find_by_id(self, user_id: UUID) -> User | None:
        record = self._session.get(UserModel, user_id)
        return self._to_entity(record) if record is not None else None

    def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[User]:
        records = (
            self._session.execute(
                select(UserModel).order_by(UserModel.created_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        return [self._to_entity(record) for record in records]

    def count_all(self) -> int:
        total = self._session.execute(select(func.count()).select_from(UserModel)).scalar_one()
        return int(total)

    # -------------------------------------------------------------
    # Escrita
    # -------------------------------------------------------------
    def save(self, user: User) -> User:
        existing = self._session.get(UserModel, user.id)
        if existing is None:
            new_model = self._to_model(user)
            self._session.add(new_model)
            persistent_record = new_model
        else:
            self._apply_changes(existing, user)
            persistent_record = existing

        self._session.flush()
        return self._to_entity(persistent_record)

    def delete_by_id(self, user_id: UUID) -> bool:
        record = self._session.get(UserModel, user_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

    # -------------------------------------------------------------
    # Mapeamento
    # -------------------------------------------------------------
    @staticmethod
    def _to_model(user: User) -> UserModel:
        return UserModel(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def _apply_changes(target: UserModel, source: User) -> None:
        target.email = source.email
        target.password_hash = source.password_hash
        target.role = source.role
        target.is_active = source.is_active

    @staticmethod
    def _to_entity(record: UserModel) -> User:
        return User(
            id=record.id,
            email=record.email,
            password_hash=record.password_hash,
            role=record.role,
            is_active=record.is_active,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
