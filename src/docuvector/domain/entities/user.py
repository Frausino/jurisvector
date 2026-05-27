"""Entidade User da camada de domínio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from docuvector.domain.enums import UserRole


def _utc_now() -> datetime:
    """Timestamp timezone-aware em UTC.

    Encapsulado para facilitar mock em testes e evitar `datetime.utcnow()`,
    que é depreciado em Python 3.12+ por retornar datetime naive.
    """
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class User:
    """Usuário do sistema.

    Imutável (frozen) para evitar mutação acidental fora de repositórios.
    Slots reduzem footprint de memória e capturam erros de digitação em atributos.
    """

    email: str
    password_hash: str
    role: UserRole
    id: UUID = field(default_factory=uuid4)
    is_active: bool = True
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def is_admin(self) -> bool:
        """Resposta semântica de papel; usada em decisões de autorização."""
        return self.role is UserRole.ADMIN

    def can_access_document_owned_by(self, owner_id: UUID) -> bool:
        """Autorização por objeto: regra central de multi-tenant.

        Usuário comum acessa apenas documentos próprios.
        Administrador acessa qualquer documento.
        """
        return self.is_admin() or self.id == owner_id
