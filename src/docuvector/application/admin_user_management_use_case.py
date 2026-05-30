"""Caso de uso de administração de usuários (admin-only).

Operações que SÓ admins podem executar:
- listar todos os usuários (paginado)
- criar usuário com role arbitrária
- deletar usuário (com chunks e docs em CASCADE)
- alterar papel de um usuário

Regras anti-bricking aplicadas:
- Admin NUNCA pode deletar a si mesmo.
- Admin NUNCA pode rebaixar a si mesmo.

Audit log para TODAS as ações.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, AuditStatus, UserRole
from docuvector.domain.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from docuvector.domain.interfaces.audit_repository import AuditRepository
from docuvector.domain.interfaces.password_hasher import PasswordHasher
from docuvector.domain.interfaces.password_policy_validator import (
    PasswordPolicyValidator,
)
from docuvector.domain.interfaces.user_repository import UserRepository

_RESOURCE_TYPE = "user"
_MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class UserListPage:
    """Página de usuários para o admin dashboard."""

    items: Sequence[User]
    total: int
    limit: int
    offset: int


class AdminUserManagementUseCase:
    """Operações administrativas sobre o catálogo de usuários."""

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

    # -------------------------------------------------------------
    # Listagem
    # -------------------------------------------------------------
    def list_users(self, limit: int = 50, offset: int = 0) -> UserListPage:
        normalized_limit = self._normalize_limit(limit)
        normalized_offset = max(0, offset)
        items = self._users.list_all(limit=normalized_limit, offset=normalized_offset)
        total = self._users.count_all()
        return UserListPage(
            items=items,
            total=total,
            limit=normalized_limit,
            offset=normalized_offset,
        )

    # -------------------------------------------------------------
    # Criação
    # -------------------------------------------------------------
    def create_user(
        self,
        acting_admin_id: UUID,
        email: str,
        plain_password: str,
        role: UserRole,
        client_ip: str | None,
        user_agent: str | None,
    ) -> User:
        """Cria usuário com papel arbitrário (incluindo admin).

        Admin assume responsabilidade pelo cadastro: aqui levantamos
        `DuplicateResourceError` normalmente (não há motivo de
        ocultar email duplicado para admin autenticado).
        """
        normalized_email = email.strip().lower()
        self._policy.validate(plain_password, owner_identifier=normalized_email)
        self._reject_if_email_already_in_use(normalized_email)

        password_hash = self._hasher.hash(plain_password)
        new_user = User(
            email=normalized_email,
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        persisted = self._users.save(new_user)

        self._audit.append(
            AuditEvent(
                actor_user_id=acting_admin_id,
                action=AuditAction.USER_CREATED_BY_ADMIN,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=persisted.id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={
                    "created_email": persisted.email,
                    "assigned_role": persisted.role.value,
                },
            )
        )
        return persisted

    # -------------------------------------------------------------
    # Exclusão
    # -------------------------------------------------------------
    def delete_user(
        self,
        acting_admin_id: UUID,
        target_user_id: UUID,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        if acting_admin_id == target_user_id:
            raise AuthorizationError("Administrador não pode excluir a própria conta.")

        target_user = self._require_user(target_user_id)

        deleted = self._users.delete_by_id(target_user_id)
        if not deleted:
            raise ResourceNotFoundError("Usuário não encontrado.")

        self._audit.append(
            AuditEvent(
                actor_user_id=acting_admin_id,
                action=AuditAction.USER_DELETED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=target_user_id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={
                    "deleted_email": target_user.email,
                    "deleted_role": target_user.role.value,
                },
            )
        )

    # -------------------------------------------------------------
    # Alteração de papel
    # -------------------------------------------------------------
    def change_role(
        self,
        acting_admin_id: UUID,
        target_user_id: UUID,
        new_role: UserRole,
        client_ip: str | None,
        user_agent: str | None,
    ) -> User:
        if acting_admin_id == target_user_id and new_role is UserRole.USER:
            raise AuthorizationError("Administrador não pode rebaixar o próprio papel.")

        target_user = self._require_user(target_user_id)
        if target_user.role is new_role:
            return target_user

        updated_user = User(
            id=target_user.id,
            email=target_user.email,
            password_hash=target_user.password_hash,
            role=new_role,
            is_active=target_user.is_active,
            created_at=target_user.created_at,
            updated_at=target_user.updated_at,
        )
        persisted = self._users.save(updated_user)

        self._audit.append(
            AuditEvent(
                actor_user_id=acting_admin_id,
                action=AuditAction.USER_ROLE_CHANGED,
                status=AuditStatus.SUCCESS,
                resource_type=_RESOURCE_TYPE,
                resource_id=target_user_id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={
                    "previous_role": target_user.role.value,
                    "new_role": new_role.value,
                },
            )
        )
        return persisted

    # -------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------
    def _require_user(self, user_id: UUID) -> User:
        user = self._users.find_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("Usuário não encontrado.")
        return user

    def _reject_if_email_already_in_use(self, normalized_email: str) -> None:
        existing = self._users.find_by_email(normalized_email)
        if existing is not None:
            raise DuplicateResourceError("Este e-mail já está cadastrado.")

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if limit <= 0:
            raise ValidationError("`limit` deve ser positivo.")
        return min(limit, _MAX_PAGE_SIZE)
