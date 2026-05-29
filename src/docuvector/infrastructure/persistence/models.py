"""Modelos ORM SQLAlchemy.

Estrutura espelha `docs/diagrams/er.puml`. Nenhum modelo ORM expõe
diretamente para a camada de aplicação; repositórios traduzem para
entidades de domínio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from docuvector.domain.enums import AuditAction, AuditStatus, UserRole


def _utc_now() -> datetime:
    """Timestamp timezone-aware em UTC para defaults do ORM."""
    return datetime.now(UTC)


def _enum_values(enum_class: type[Enum]) -> list[str]:
    """Retorna os values do enum para serialização no Postgres.

    Sem isso, SQLAlchemy envia o NOME do membro (`LOGIN_FAILED`) em vez
    do value (`login_failed`), quebrando contra o enum criado na migration.
    """
    return [member.value for member in enum_class]


class Base(DeclarativeBase):
    """Base declarativa raiz de todos os modelos ORM.

    Usar uma única Base por aplicação é prática recomendada do SQLAlchemy 2.0
    e permite ao Alembic detectar todas as tabelas a partir de `Base.metadata`.
    """


# =============================================================
# users
# =============================================================
class UserModel(Base):
    """Tabela `users`. Persistência da entidade `User` do domínio."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            name="user_role",
            values_callable=_enum_values,
            native_enum=True,
        ),
        nullable=False,
        default=UserRole.USER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    documents: Mapped[list[DocumentModel]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )


# =============================================================
# documents
# =============================================================
class DocumentModel(Base):
    """Tabela `documents`. Metadados; vetores ficam no ChromaDB."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    compression_method: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    original_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compressed_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    semantic_retention: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    ingest_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    owner: Mapped[UserModel] = relationship(back_populates="documents")


# =============================================================
# audit_logs
# =============================================================
class AuditLogModel(Base):
    """Tabela `audit_logs`. Append-only. Persistência da entidade `AuditEvent`."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[AuditAction] = mapped_column(
        SqlEnum(
            AuditAction,
            name="audit_action",
            values_callable=_enum_values,
            native_enum=True,
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[AuditStatus] = mapped_column(
        SqlEnum(
            AuditStatus,
            name="audit_status",
            values_callable=_enum_values,
            native_enum=True,
        ),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        index=True,
    )
