"""Schemas Pydantic para autenticação e gestão de usuários."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from docuvector.domain.enums import UserRole


# =============================================================
# Login
# =============================================================
class LoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    token_type: str
    expires_in: int


# =============================================================
# Registro público
# =============================================================
class RegisterRequest(BaseModel):
    """Payload de auto-cadastro.

    Validação real da senha (política NIST) acontece no use case.
    Pydantic só rejeita strings absurdamente longas.
    """

    model_config = ConfigDict(frozen=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegistrationAcknowledgement(BaseModel):
    """Resposta GENÉRICA do /register (defesa anti-enumeração).

    Mesmo conteúdo para criação real e para email já existente.
    NÃO inclui o `id` nem o `email` confirmado, porque devolver isso
    seria recriar o vazamento de enumeração que estamos eliminando.
    """

    model_config = ConfigDict(frozen=True)

    message: str


# =============================================================
# Representação pública de User
# =============================================================
class UserResponse(BaseModel):
    """Forma pública de um usuário. Nunca inclui `password_hash`."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


# =============================================================
# Admin endpoints
# =============================================================
class AdminCreateUserRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    role: UserRole = UserRole.USER


class AdminChangeRoleRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: UserRole


class UserListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[UserResponse]
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
