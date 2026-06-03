"""audit ledger decoupled from users

Revision ID: 0004_audit_decoupled
Revises: 02e0ae67b1f1
Create Date: 2026-05-30 18:30:00.000000

Refatora `audit_logs` de "apêndice de users" para "ledger imutável":

1.  Remove a foreign key `audit_logs.user_id -> users.id` (era
    ON DELETE SET NULL). Eventos passam a ser registros históricos:
    o usuário pode ser deletado sem que o registro sofra mutação.

2.  Renomeia `user_id` → `actor_user_id` para deixar a semântica
    clara no schema. Continua sendo UUID nullable, mantendo eventos
    sem autor (ex.: login com e-mail inexistente).

3.  Adiciona snapshots de contexto que viajam com o evento:
    - `actor_email` (TEXT, nullable): email do usuário no momento.
    - `actor_role` (ENUM user_role, nullable): papel histórico.
    - `correlation_id` (UUID, nullable): agrupa eventos da operação.

4.  Mantém todos os índices úteis e adiciona índice sobre
    `actor_user_id` (substituto do índice que vinha junto da FK) e
    sobre `correlation_id` (queries de trilha forense).

Upgrade preserva dados existentes: rename mantém valores; campos novos
ficam NULL nos eventos antigos, o que é semanticamente correto (não
temos snapshot do que não foi capturado historicamente).

Downgrade RECRIA a FK; se houver eventos com `actor_user_id` apontando
para users que foram deletados, a recriação da FK falha. Em produção,
antes de rodar o downgrade seria necessário limpar esses órfãos.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0004_audit_decoupled"
down_revision: str | None = "02e0ae67b1f1" # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reusa o tipo `user_role` criado pela migration 0001. `create_type=False`
# evita tentar recriar o tipo (já existe no banco).
_USER_ROLE_ENUM = ENUM(
    "admin",
    "user",
    name="user_role",
    create_type=False,
)


def upgrade() -> None:
    # -------------------------------------------------------------
    # 1) Remove FK audit_logs.user_id -> users.id
    # -------------------------------------------------------------
    op.drop_constraint(
        "audit_logs_user_id_fkey",
        "audit_logs",
        type_="foreignkey",
    )

    # -------------------------------------------------------------
    # 2) Renomeia user_id -> actor_user_id (mantém tipo e nullable)
    # -------------------------------------------------------------
    op.alter_column(
        "audit_logs",
        "user_id",
        new_column_name="actor_user_id",
    )

    # -------------------------------------------------------------
    # 3) Snapshots de contexto + correlation_id
    # -------------------------------------------------------------
    op.add_column(
        "audit_logs",
        sa.Column("actor_email", sa.Text(), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("actor_role", _USER_ROLE_ENUM, nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("correlation_id", PG_UUID(as_uuid=True), nullable=True),
    )

    # -------------------------------------------------------------
    # 4) Índices forenses
    # -------------------------------------------------------------
    op.create_index(
        "ix_audit_logs_actor_user_id",
        "audit_logs",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_audit_logs_correlation_id",
        "audit_logs",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_correlation_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")

    op.drop_column("audit_logs", "correlation_id")
    op.drop_column("audit_logs", "actor_role")
    op.drop_column("audit_logs", "actor_email")

    op.alter_column(
        "audit_logs",
        "actor_user_id",
        new_column_name="user_id",
    )

    # Recria FK. ATENÇÃO: falha se houver órfãos (user deletado mas
    # com eventos preservados). Limpar antes em produção.
    op.create_foreign_key(
        "audit_logs_user_id_fkey",
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
