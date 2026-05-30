"""Script idempotente para garantir o admin de bootstrap.

Diferença vs. o antigo `seed_users.py`:
- Cria APENAS o admin definido em `SEED_ADMIN_*`.
- Todos os demais usuários nascem via `POST /api/v1/auth/register`.

Executar:

    just seed-admin
    # ou
    uv run seed-admin

Se o admin já existe no banco, o script não faz nada (idempotente).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from uuid import uuid4

from docuvector.config.settings import Settings, get_settings
from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole
from docuvector.infrastructure.logging.structlog_config import configure_logging, get_logger
from docuvector.infrastructure.persistence.audit_repository_impl import (
    SqlAlchemyAuditRepository,
)
from docuvector.infrastructure.persistence.database import get_session_factory
from docuvector.infrastructure.persistence.user_repository_impl import (
    SqlAlchemyUserRepository,
)
from docuvector.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher

_RESOURCE_TYPE = "user"


def _ensure_admin_exists(settings: Settings) -> tuple[User, bool]:
    """Cria o admin se ele não existir. Retorna (user, was_created).

    Comportamento garante que reexecuções não duplicam o usuário e
    não sobrescrevem a senha caso ela tenha sido alterada via API.
    """
    session_factory = get_session_factory()
    hasher = BcryptPasswordHasher(rounds=settings.effective_bcrypt_rounds)

    with session_factory() as session:
        user_repository = SqlAlchemyUserRepository(session)
        normalized_admin_email = settings.seed_admin_email.strip().lower()

        existing_admin = user_repository.find_by_email(normalized_admin_email)
        if existing_admin is not None:
            return existing_admin, False

        admin_user = User(
            id=uuid4(),
            email=normalized_admin_email,
            password_hash=hasher.hash(settings.seed_admin_password.get_secret_value()),
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        persisted_admin = user_repository.save(admin_user)
        session.commit()
        return persisted_admin, True


def _emit_seed_audit(admin_user: User, was_created: bool) -> None:
    """Registra o seed no audit log para rastreabilidade.

    Passa o `User` inteiro (em vez de só o id) para popular snapshots
    de `actor_email` e `actor_role` no evento. Assim o ledger forense
    preserva a identidade do admin no momento do seed, sobrevivendo
    a qualquer mudança ou deleção futura.
    """
    audit_repository = SqlAlchemyAuditRepository(get_session_factory())
    audit_repository.append(
        AuditEvent(
            actor_user_id=admin_user.id,
            actor_email=admin_user.email,
            actor_role=admin_user.role,
            action=AuditAction.USER_SEEDED,
            status=AuditStatus.SUCCESS,
            resource_type=_RESOURCE_TYPE,
            resource_id=admin_user.id,
            ip_address=None,
            user_agent="seed-admin-script",
            metadata={
                "was_created": was_created,
                "executed_at": int(datetime.now(UTC).timestamp()),
            },
        )
    )


def main() -> int:
    """Entrypoint do script. Retorna código de saída para shell."""
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger("docuvector.seed_admin")

    try:
        admin_user, was_created = _ensure_admin_exists(settings)
    except Exception as failure:  # noqa: BLE001 - script CLI: log e exit
        logger.exception("seed_admin_failed", reason=str(failure))
        return 1

    _emit_seed_audit(admin_user, was_created)

    if was_created:
        logger.info(
            "seed_admin_created",
            admin_email=admin_user.email,
            admin_id=str(admin_user.id),
        )
    else:
        logger.info(
            "seed_admin_already_exists",
            admin_email=admin_user.email,
            admin_id=str(admin_user.id),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
