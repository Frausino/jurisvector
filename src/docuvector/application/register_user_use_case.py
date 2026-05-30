"""Caso de uso de registro público de usuário.

Auto-cadastro via `POST /api/v1/auth/register`. Sempre cria papel
`user`; promoção a admin é exclusiva de `PATCH /admin/users/{id}/role`.

Defesa anti-enumeração COMPLETA:

1.  `is_new` no resultado sinaliza se foi criação real ou caminho de
    dummy. O ROUTER ignora esse flag na resposta HTTP, retornando 201
    genérico em ambos os casos. O fluxo real (notificação por email
    out-of-band, futuro) usa o flag.

2.  Quando o email JÁ existe, executamos um hash bcrypt dummy de
    custo igual ao real. Sem isso, o caminho "duplicado" pula o
    bcrypt e termina ~250ms mais rápido que o caminho "novo",
    revelando a existência do email por timing.

3.  Nenhuma exceção é levantada por duplicidade. O caller recebe um
    resultado que parece sucesso, com o usuário ORIGINAL se já existia.
"""

from __future__ import annotations

from dataclasses import dataclass

from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole
from docuvector.domain.interfaces.audit_repository import AuditRepository
from docuvector.domain.interfaces.password_hasher import PasswordHasher
from docuvector.domain.interfaces.password_policy_validator import (
    PasswordPolicyValidator,
)
from docuvector.domain.interfaces.user_repository import UserRepository

_RESOURCE_TYPE = "user"


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    """Resultado do registro.

    `was_created=True` indica criação real. `was_created=False` indica
    que o email já existia: o `user` retornado é o usuário ORIGINAL
    (não o que tentou se cadastrar), e o caller NÃO DEVE expor essa
    distinção no contrato HTTP.
    """

    user: User
    was_created: bool


class RegisterUserUseCase:
    """Auto-cadastro de usuário comum com defesa anti-enumeração."""

    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicyValidator,
        audit_repository: AuditRepository,
    ) -> None:
        self._users = user_repository
        self._hasher = password_hasher
        self._policy = password_policy
        self._audit = audit_repository

    def register(
        self,
        email: str,
        plain_password: str,
        client_ip: str | None,
        user_agent: str | None,
    ) -> RegistrationResult:
        """Registra ou simula registro (anti-enum). NUNCA levanta DuplicateResourceError."""
        normalized_email = email.strip().lower()

        # Política é validada ANTES de qualquer consulta ao banco, em ambos
        # os caminhos. Garante mesma latência inicial e mesma resposta de
        # erro para senhas fracas, independente do email existir ou não.
        self._policy.validate(plain_password, owner_identifier=normalized_email)

        existing_user = self._users.find_by_email(normalized_email)
        if existing_user is not None:
            return self._simulate_registration_for_existing_email(
                existing_user=existing_user,
                plain_password=plain_password,
                client_ip=client_ip,
                user_agent=user_agent,
            )

        return self._perform_real_registration(
            normalized_email=normalized_email,
            plain_password=plain_password,
            client_ip=client_ip,
            user_agent=user_agent,
        )

    # -------------------------------------------------------------
    # Caminhos do fluxo
    # -------------------------------------------------------------
    def _perform_real_registration(
        self,
        normalized_email: str,
        plain_password: str,
        client_ip: str | None,
        user_agent: str | None,
    ) -> RegistrationResult:
        password_hash = self._hasher.hash(plain_password)
        new_user = User(
            email=normalized_email,
            password_hash=password_hash,
            role=UserRole.USER,
            is_active=True,
        )
        persisted = self._users.save(new_user)
        self._audit_outcome(
            user=persisted,
            audit_status=AuditStatus.SUCCESS,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return RegistrationResult(user=persisted, was_created=True)

    def _simulate_registration_for_existing_email(
        self,
        existing_user: User,
        plain_password: str,
        client_ip: str | None,
        user_agent: str | None,
    ) -> RegistrationResult:
        """Executa hash dummy para igualar latência ao caminho real.

        Calculamos o hash mas DESCARTAMOS o resultado: nenhum dado é
        persistido. O audit log marca a tentativa como FAILURE para
        permitir detecção forense de enumeração (mesmo IP repetindo
        emails) sem comprometer a indistinguibilidade externa.
        """
        _discarded_hash = self._hasher.hash(plain_password)
        del _discarded_hash

        self._audit.append(
            AuditEvent(
                actor_user_id=existing_user.id,
                actor_email=existing_user.email,
                actor_role=existing_user.role,
                action=AuditAction.USER_REGISTERED,
                status=AuditStatus.FAILURE,
                resource_type=_RESOURCE_TYPE,
                resource_id=existing_user.id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={
                    "email": existing_user.email,
                    "reason": "email_already_registered",
                },
            )
        )
        return RegistrationResult(user=existing_user, was_created=False)

    def _audit_outcome(
        self,
        user: User,
        audit_status: AuditStatus,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self._audit.append(
            AuditEvent(
                actor_user_id=user.id,
                actor_email=user.email,
                actor_role=user.role,
                action=AuditAction.USER_REGISTERED,
                status=audit_status,
                resource_type=_RESOURCE_TYPE,
                resource_id=user.id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"email": user.email, "role": user.role.value},
            )
        )
