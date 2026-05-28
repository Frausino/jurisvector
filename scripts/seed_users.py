"""Seed idempotente dos usuários iniciais do DocuVector Lite.

Cria 3 usuários a partir do `.env`: 1 administrador + 2 usuários comuns.
Idempotência: rodar duas vezes não duplica. Falha-rápido se faltar
qualquer credencial obrigatória.

Uso (Windows PowerShell):
    uv run python -m scripts.seed_users

Saída em logs estruturados (structlog). Senhas NUNCA são logadas.

Decisões registradas:
- Não persistimos a senha em claro em momento algum.
- Hash bcrypt cost 12 (mesmo do runtime).
- Audit log gera evento USER_SEEDED para cada criação.
- Se usuário já existe, NÃO sobrescreve. Permite re-execução segura
  do script em ambientes onde o operador trocou apenas uma senha
  diretamente no banco (vale rastreabilidade vs comodidade).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from pydantic import SecretStr

from docuvector.config.settings import Settings, get_settings
from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole
from docuvector.infrastructure.logging.structlog_config import configure_logging, get_logger
from docuvector.infrastructure.persistence.audit_repository_impl import SqlAlchemyAuditRepository
from docuvector.infrastructure.persistence.database import get_session_factory
from docuvector.infrastructure.persistence.user_repository_impl import SqlAlchemyUserRepository
from docuvector.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


@dataclass(frozen=True, slots=True)
class SeedSpecification:
    """Especificação declarativa de um usuário a ser seedado."""

    email: str
    password: SecretStr
    role: UserRole


def _build_seed_specifications(settings: Settings) -> list[SeedSpecification]:
    """Constrói a lista canônica de usuários iniciais a partir do Settings."""
    return [
        SeedSpecification(
            email=settings.seed_admin_email,
            password=settings.seed_admin_password,
            role=UserRole.ADMIN,
        ),
        SeedSpecification(
            email=settings.seed_user1_email,
            password=settings.seed_user1_password,
            role=UserRole.USER,
        ),
        SeedSpecification(
            email=settings.seed_user2_email,
            password=settings.seed_user2_password,
            role=UserRole.USER,
        ),
    ]


def main() -> int:
    """Executa o seed. Retorna exit code adequado para CI/CD."""
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger("docuvector.seed_users")

    logger.info("seed_users_started", environment=settings.app_env.value)

    session_factory = get_session_factory()
    password_hasher = BcryptPasswordHasher()
    audit_repository = SqlAlchemyAuditRepository(session_factory)
    seed_specifications = _build_seed_specifications(settings)

    created_count = 0
    skipped_count = 0

    for specification in seed_specifications:
        normalized_email = specification.email.lower().strip()

        try:
            with session_factory() as session:
                user_repository = SqlAlchemyUserRepository(session)
                already_existing_user = user_repository.find_by_email(normalized_email)

                if already_existing_user is not None:
                    logger.info(
                        "user_already_exists",
                        email=normalized_email,
                        role=already_existing_user.role.value,
                    )
                    skipped_count += 1
                    continue

                password_hash = password_hasher.hash(specification.password.get_secret_value())
                new_user = User(
                    email=normalized_email,
                    password_hash=password_hash,
                    role=specification.role,
                )
                persisted_user = user_repository.save(new_user)
                session.commit()

                audit_repository.append(
                    AuditEvent(
                        action=AuditAction.USER_SEEDED,
                        status=AuditStatus.SUCCESS,
                        resource_type="user",
                        user_id=persisted_user.id,
                        resource_id=persisted_user.id,
                        metadata={"email": normalized_email, "role": specification.role.value},
                    ),
                )

                logger.info(
                    "user_seeded",
                    email=normalized_email,
                    role=specification.role.value,
                )
                created_count += 1

        except Exception as seed_error:  # noqa: BLE001 - boundary do script CLI
            logger.error(
                "seed_user_failed",
                email=normalized_email,
                error=str(seed_error),
                exc_info=True,
            )
            return EXIT_FAILURE

    logger.info(
        "seed_users_finished",
        created=created_count,
        skipped=skipped_count,
        total=len(seed_specifications),
    )
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
