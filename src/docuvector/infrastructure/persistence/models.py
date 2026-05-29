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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from docuvector.domain.enums import (
    AuditAction,
    AuditStatus,
    DocumentStatus,
    EmbeddingProviderName,
    FileFormat,
    UserRole,
)


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
    """Tabela `documents`. Metadados; vetores ficam no ChromaDB.

    Campos de compressão (compression_method, original_dimension, etc.)
    permanecem nullable e são preenchidos pela Sprint 4 (benchmark de
    compressão de embeddings). Na Sprint 3, ficam vazios.
    """

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
    file_format: Mapped[FileFormat] = mapped_column(
        SqlEnum(
            FileFormat,
            name="file_format",
            values_callable=_enum_values,
            native_enum=True,
        ),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        SqlEnum(
            DocumentStatus,
            name="document_status",
            values_callable=_enum_values,
            native_enum=True,
        ),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reservados para Sprint 4 (compressão de embeddings).
    compression_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    chunks: Mapped[list[DocumentChunkModel]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Dedup por dono: mesmo conteúdo não pode ser ingerido duas vezes.
        UniqueConstraint(
            "owner_id",
            "checksum_sha256",
            name="uq_documents_owner_checksum",
        ),
        # Filtro frequente: documentos do usuário em determinado status.
        Index("ix_documents_owner_status", "owner_id", "status"),
    )


# =============================================================
# document_chunks
# =============================================================
class DocumentChunkModel(Base):
    """Tabela `document_chunks`. Pedaços vetorizados de um documento.

    `owner_id` é denormalizado a partir de `documents` para filtrar
    sem JOIN em queries multi-tenant frequentes. Embedding propriamente
    dito vive no ChromaDB; aqui ficam metadados (provider, model, dim).
    """

    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_provider: Mapped[EmbeddingProviderName] = mapped_column(
        SqlEnum(
            EmbeddingProviderName,
            name="embedding_provider_name",
            values_callable=_enum_values,
            native_enum=True,
        ),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    document: Mapped[DocumentModel] = relationship(back_populates="chunks")

    __table_args__ = (
        # Recuperação ordenada de chunks por documento.
        Index("ix_document_chunks_document_index", "document_id", "chunk_index"),
        # Unicidade do par (documento, índice) evita duplicação acidental.
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
    )


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
    event_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        index=True,
    )
