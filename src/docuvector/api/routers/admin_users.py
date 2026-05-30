"""Endpoints REST administrativos sobre usuários."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from docuvector.api.deps import (
    AdminTokenDependency,
    AdminUserManagementUseCaseDependency,
    ClientIpDependency,
)
from docuvector.api.schemas.auth import (
    AdminChangeRoleRequest,
    AdminCreateUserRequest,
    UserListResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])


# =============================================================
# GET /api/v1/admin/users
# =============================================================
@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar usuários do sistema (admin)",
    responses={403: {"description": "Apenas administradores podem listar usuários."}},
)
def list_users(
    _admin: AdminTokenDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
    limit: int = 50,
    offset: int = 0,
) -> UserListResponse:
    page = admin_use_case.list_users(limit=limit, offset=offset)
    return UserListResponse(
        items=[UserResponse.model_validate(user) for user in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


# =============================================================
# POST /api/v1/admin/users
# =============================================================
@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar usuário (admin)",
    responses={
        403: {"description": "Apenas administradores podem criar usuários."},
        409: {"description": "E-mail já cadastrado."},
        422: {"description": "Senha não atende à política."},
    },
)
def create_user(
    request: Request,
    payload: AdminCreateUserRequest,
    admin_token: AdminTokenDependency,
    client_ip: ClientIpDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
) -> UserResponse:
    user_agent_header = request.headers.get("user-agent")
    created = admin_use_case.create_user(
        acting_admin_id=admin_token.user_id,
        email=payload.email,
        plain_password=payload.password,
        role=payload.role,
        client_ip=client_ip,
        user_agent=user_agent_header,
    )
    return UserResponse.model_validate(created)


# =============================================================
# DELETE /api/v1/admin/users/{id}
# =============================================================
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir usuário (admin)",
    responses={
        403: {
            "description": (
                "Apenas administradores podem excluir, e admin não pode excluir a própria conta."
            )
        },
        404: {"description": "Usuário não encontrado."},
    },
)
def delete_user(
    user_id: UUID,
    request: Request,
    admin_token: AdminTokenDependency,
    client_ip: ClientIpDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
) -> None:
    user_agent_header = request.headers.get("user-agent")
    admin_use_case.delete_user(
        acting_admin_id=admin_token.user_id,
        target_user_id=user_id,
        client_ip=client_ip,
        user_agent=user_agent_header,
    )


# =============================================================
# PATCH /api/v1/admin/users/{id}/role
# =============================================================
@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Alterar papel de usuário (admin)",
    responses={
        403: {"description": "Admin não pode rebaixar a si mesmo."},
        404: {"description": "Usuário não encontrado."},
    },
)
def change_role(
    user_id: UUID,
    request: Request,
    payload: AdminChangeRoleRequest,
    admin_token: AdminTokenDependency,
    client_ip: ClientIpDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
) -> UserResponse:
    user_agent_header = request.headers.get("user-agent")
    updated = admin_use_case.change_role(
        acting_admin_id=admin_token.user_id,
        target_user_id=user_id,
        new_role=payload.role,
        client_ip=client_ip,
        user_agent=user_agent_header,
    )
    return UserResponse.model_validate(updated)
