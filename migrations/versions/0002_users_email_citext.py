"""Alter users.email to CITEXT for case-insensitive uniqueness.

Revision ID: 0002_users_email_citext
Revises: 0001_initial
Create Date: 2026-05-28 22:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision: str = "0002_users_email_citext"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext";')
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(length=255),
        type_=CITEXT(),
        existing_nullable=False,
        postgresql_using="email::citext",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "email",
        existing_type=CITEXT(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="email::text",
    )
