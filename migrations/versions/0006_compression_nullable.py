"""relax NOT NULL on documents.compression_method

Revision ID: 0005_relax_compression_method_null
Revises: 0004_audit_decoupled
Create Date: 2026-05-31 02:30:00.000000

Corrige drift entre o `DocumentModel` (que declara
`compression_method: Mapped[str | None]`, nullable) e o schema real
do Postgres, onde a migration `0001_initial` criou a coluna como
`NOT NULL` com `server_default='none'`.

Conforme o `models.py` evoluiu para `nullable=True`, o SQLAlchemy 2.0
passou a enviar `NULL` explícito no INSERT (sobrescrevendo o
`server_default`), o que disparava a constraint NOT NULL no banco.

Decisão: a coluna fica nullable até que a Sprint 4 (benchmark de
compressão) defina o que gravar. `server_default` removido porque a
camada de aplicação deve ser explícita sobre o método de compressão;
default `'none'` mascarava ausência de implementação.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_compression_nullable"
down_revision: str | None = "0004_audit_decoupled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "documents",
        "compression_method",
        existing_type=sa.String(32),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE documents SET compression_method = 'none' "
        "WHERE compression_method IS NULL"
    )
    op.alter_column(
        "documents",
        "compression_method",
        existing_type=sa.String(32),
        nullable=False,
        server_default="none",
    )
