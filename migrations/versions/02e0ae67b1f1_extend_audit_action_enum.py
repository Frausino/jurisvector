"""extend audit_action enum"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "02e0ae67b1f1"
down_revision: Union[str, None] = "0003_documents_and_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE audit_action "
        "ADD VALUE IF NOT EXISTS 'user_registered';"
    )

    op.execute(
        "ALTER TYPE audit_action "
        "ADD VALUE IF NOT EXISTS 'user_created_by_admin';"
    )

    op.execute(
        "ALTER TYPE audit_action "
        "ADD VALUE IF NOT EXISTS 'user_deleted';"
    )

    op.execute(
        "ALTER TYPE audit_action "
        "ADD VALUE IF NOT EXISTS 'user_role_changed';"
    )


def downgrade() -> None:
    # PostgreSQL não suporta remover valores ENUM de forma simples.
    pass
