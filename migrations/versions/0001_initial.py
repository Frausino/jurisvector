"""initial schema: users, documents, audit_logs

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-26 22:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, INET, JSONB, UUID as PG_UUID
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_ROLE_ENUM = ENUM(
    "admin",
    "user",
    name="user_role",
    create_type=False,
)

AUDIT_ACTION_ENUM = ENUM(
    "login_success",
    "login_failed",
    "user_seeded",
    "access_denied",
    "document_uploaded",
    "document_deleted",
    "document_updated",
    "query_executed",
    name="audit_action",
    create_type=False,
)

AUDIT_STATUS_ENUM = ENUM(
    "success",
    "failure",
    "forbidden",
    name="audit_status",
    create_type=False,
)

def upgrade() -> None:
    # Garantia idempotente: extensões já são criadas pelo init.sql do Docker,
    # mas repetir aqui torna a migration auto-suficiente para outros ambientes.
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext";')

    USER_ROLE_ENUM.create(op.get_bind(), checkfirst=True)
    AUDIT_ACTION_ENUM.create(op.get_bind(), checkfirst=True)
    AUDIT_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", USER_ROLE_ENUM, nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "documents",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_format", sa.String(16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("chunks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_provider", sa.String(32), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("compression_method", sa.String(32), nullable=False, server_default="none"),
        sa.Column("original_dimension", sa.Integer(), nullable=True),
        sa.Column("compressed_dimension", sa.Integer(), nullable=True),
        sa.Column("semantic_retention", sa.Numeric(5, 4), nullable=True),
        sa.Column("ingest_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", AUDIT_ACTION_ENUM, nullable=False),
        sa.Column("status", AUDIT_STATUS_ENUM, nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_documents_owner_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_table("users")

    AUDIT_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    AUDIT_ACTION_ENUM.drop(op.get_bind(), checkfirst=True)
    USER_ROLE_ENUM.drop(op.get_bind(), checkfirst=True)
