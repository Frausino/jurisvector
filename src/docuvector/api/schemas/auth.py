"""Schemas Pydantic de entrada e saída do router de autenticação.

São contratos HTTP, não entidades de domínio. Mantemos separados
para que o formato wire possa evoluir sem afetar o domínio.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from docuvector.domain.enums import UserRole


class LoginRequest(BaseModel):
    """Payload de login. Restritivo: só email e senha, nada mais.

    `extra="forbid"` bloqueia mass assignment: cliente não pode tentar
    enviar `role` ou `is_active` no corpo.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr = Field(description="E-mail do usuário.")
    password: str = Field(min_length=1, description="Senha em claro.")


class LoginResponse(BaseModel):
    """Resposta do login bem-sucedido."""

    access_token: str = Field(description="JWT serializado.")
    token_type: str = Field(default="bearer", description="Tipo do token.")
    expires_in: int = Field(description="Tempo de vida em segundos.")


class UserResponse(BaseModel):
    """Representação pública do usuário.

    NUNCA inclui `password_hash`. Restringe quais campos a API expõe.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool


class ErrorResponse(BaseModel):
    """Formato padronizado de erro da API."""

    error: dict[str, str | dict[str, str]]
