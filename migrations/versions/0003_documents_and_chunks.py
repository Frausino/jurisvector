"""sprint 3 - rag domain: documents conformance + document_chunks

Revision ID: 0003_documents_and_chunks
Revises: 0002_users_email_citext
Create Date: 2026-05-29 10:00:00.000000

Esta migration faz duas coisas:

1.  Conforma a tabela `documents` ao domínio da Sprint 3:
    - Cria os enums Postgres `file_format` e `document_status`.
    - Converte as colunas `file_format` e `status` de String para enum.
    - Adiciona `checksum_sha256` (NOT NULL) e `failure_reason` (nullable).
    - Remove `chunks_count`, `embedding_provider`, `embedding_model`
      (esses dados agora vivem em `document_chunks`).
    - Adiciona UNIQUE(owner_id, checksum_sha256) e índice composto
      (owner_id, status).

2.  Cria a tabela `document_chunks` com o enum `embedding_provider_name`,
    relação CASCADE com `documents` e índice ordenado por chunk_index.

Assume que `documents` está vazia (Sprint 2 não fez upload de nada),
o que torna seguro o ALTER COLUMN com USING e o ADD COLUMN NOT NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0003_documents_and_chunks"
down_revision: str | None = "0002_users_email_citext"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FILE_FORMAT_ENUM = ENUM(
    "pdf",
    "txt",
    "md",
    name="file_format",
    create_type=False,
)

DOCUMENT_STATUS_ENUM = ENUM(
    "uploaded",
    "extracting",
    "extracted",
    "chunking",
    "chunked",
    "embedding",
    "embedded",
    "failed",
    name="document_status",
    create_type=False,
)

EMBEDDING_PROVIDER_NAME_ENUM = ENUM(
    "openai",
    "sentence_transformers",
    name="embedding_provider_name",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    FILE_FORMAT_ENUM.create(bind, checkfirst=True)
    DOCUMENT_STATUS_ENUM.create(bind, checkfirst=True)
    EMBEDDING_PROVIDER_NAME_ENUM.create(bind, checkfirst=True)

    # -------------------------------------------------------------
    # documents: conformance
    # -------------------------------------------------------------
    # Colunas removidas (agora vivem em document_chunks).
    op.drop_column("documents", "chunks_count")
    op.drop_column("documents", "embedding_provider")
    op.drop_column("documents", "embedding_model")

    # `file_format` String -> ENUM file_format.
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN file_format TYPE file_format "
        "USING file_format::file_format"
    )

    # `status` String -> ENUM document_status.
    # Antigos valores ('pending', etc.) não devem existir porque a tabela
    # está vazia. O USING converte literais válidos; valores inesperados
    # falhariam aqui, sinalizando dados sujos antes do schema mudar.
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN status TYPE document_status "
        "USING status::document_status"
    )
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN status SET DEFAULT 'uploaded'::document_status"
    )

    op.add_column(
        "documents",
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )

    op.create_unique_constraint(
        "uq_documents_owner_checksum",
        "documents",
        ["owner_id", "checksum_sha256"],
    )
    op.create_index(
        "ix_documents_owner_status",
        "documents",
        ["owner_id", "status"],
    )

    # -------------------------------------------------------------
    # document_chunks: nova tabela
    # -------------------------------------------------------------
    op.create_table(
        "document_chunks",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_provider", EMBEDDING_PROVIDER_NAME_ENUM, nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_document_chunks_owner_id",
        "document_chunks",
        ["owner_id"],
    )
    op.create_index(
        "ix_document_chunks_document_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    # document_chunks
    op.drop_constraint("uq_document_chunks_document_index", "document_chunks", type_="unique")
    op.drop_index("ix_document_chunks_document_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_owner_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    # documents
    op.drop_index("ix_documents_owner_status", table_name="documents")
    op.drop_constraint("uq_documents_owner_checksum", "documents", type_="unique")
    op.drop_column("documents", "failure_reason")
    op.drop_column("documents", "checksum_sha256")

    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN status TYPE VARCHAR(16) "
        "USING status::text"
    )
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN status SET DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE documents "
        "ALTER COLUMN file_format TYPE VARCHAR(16) "
        "USING file_format::text"
    )

    op.add_column(
        "documents",
        sa.Column("embedding_model", sa.String(128), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("embedding_provider", sa.String(32), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("chunks_count", sa.Integer(), nullable=False, server_default="0"),
    )

    EMBEDDING_PROVIDER_NAME_ENUM.drop(bind, checkfirst=True)
    DOCUMENT_STATUS_ENUM.drop(bind, checkfirst=True)
    FILE_FORMAT_ENUM.drop(bind, checkfirst=True)
