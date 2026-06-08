"""Adiciona valores ao enum audit_action para Sprint 6.

Novos eventos:
    - retrieval_compared: comparação de retrieval entre coleções.
    - multi_collection_ingested: ingestão nas 5 coleções Chroma.

Postgres `ALTER TYPE ... ADD VALUE` é irreversível por design (downgrade
não remove valores do enum — isso é correto para um ledger de auditoria).
"""

from __future__ import annotations

from alembic import op

revision = "0007_audit_multi_collection"
down_revision = "0005_compression_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE audit_action "
        "ADD VALUE IF NOT EXISTS 'retrieval_compared';"
    )
    op.execute(
        "ALTER TYPE audit_action "
        "ADD VALUE IF NOT EXISTS 'multi_collection_ingested';"
    )


def downgrade() -> None:
    # Enum values cannot be removed in Postgres without recreating the type.
    # Downgrade is intentionally a no-op: audit ledger values are permanent.
    pass
