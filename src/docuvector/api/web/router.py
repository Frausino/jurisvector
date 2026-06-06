"""Router de views server-side (HTML) do DocuVector Lite.

Layout inspirado no Claude.ai:
- Sidebar esquerda: documentos do usuário + upload inline.
- Área principal: chat com histórico acumulado na sessão.
- Admin: painel com gestão de usuários e acesso a todos os documentos.

Princípios:
- Zero mudança no backend — consome os mesmos use cases da API REST.
- Histórico mantido no DOM via HTMX hx-swap="beforeend".
- Painel admin protegido por require_admin no router web.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse

from docuvector.api.deps import (
    SESSION_COOKIE_NAME,
    AdminUserManagementUseCaseDependency,
    AnswerUseCaseDependency,
    AuthUseCaseDependency,
    ClientIpDependency,
    CompressionBenchmarkUseCaseDependency,
    CurrentTokenDependency,
    DocumentCrudUseCaseDependency,
    EmbeddingBenchmarkUseCaseDependency,
    IngestionUseCaseDependency,
    MetricsUseCaseDependency,
    RegisterUserUseCaseDependency,
    SettingsDependency,
    get_client_ip,
)
from docuvector.api.web.templating import current_user_or_none, templates
from docuvector.application.answer_use_case import AskInput
from docuvector.application.compression_benchmark_use_case import BenchmarkInput
from docuvector.config.settings import get_settings
from docuvector.domain.enums import EmbeddingProviderName, LlmProviderName, UserRole
from docuvector.domain.exceptions import (
    AuthenticationError,
    DocuvectorError,
    ResourceNotFoundError,
)
from docuvector.infrastructure.embeddings.factory import (
    list_available_providers as list_embedding_providers,
)
from docuvector.infrastructure.embeddings.factory import (
    resolve_embedder,
)
from docuvector.infrastructure.llm.factory import (
    list_available_providers as list_llm_providers_for_env,
)
from docuvector.infrastructure.llm.factory import (
    resolve_llm_client,
)

router = APIRouter(tags=["web"], include_in_schema=False)


# ---------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------
def _set_session_cookie(response: RedirectResponse, token: str, max_age: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=not settings.is_development,
        path="/",
    )


def _require_admin(request: Request) -> RedirectResponse | None:
    """Redireciona para /app/chat se o usuário não for admin."""
    user = current_user_or_none(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role is not UserRole.ADMIN:
        return RedirectResponse(url="/app/chat", status_code=status.HTTP_303_SEE_OTHER)
    return None


# =============================================================
# Raiz
# =============================================================
@router.get("/", response_class=HTMLResponse, response_model=None)
def index(request: Request) -> RedirectResponse:
    if current_user_or_none(request) is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/app/chat", status_code=status.HTTP_303_SEE_OTHER)


# =============================================================
# Auth
# =============================================================
@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_page(request: Request) -> HTMLResponse:
    if current_user_or_none(request) is not None:
        return RedirectResponse(  # type: ignore[return-value]
            url="/app/chat", status_code=status.HTTP_303_SEE_OTHER
        )
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse, response_model=None)
def login_submit(
    request: Request,
    auth_use_case: AuthUseCaseDependency,
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    try:
        result = auth_use_case.login(
            email=email,
            plain_password=password,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthenticationError:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Email ou senha inválidos."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    redirect = RedirectResponse(url="/app/chat", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(redirect, result.access_token, result.expires_in_seconds)
    return redirect


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"error": None, "success": None})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    register_use_case: RegisterUserUseCaseDependency,
    client_ip: Annotated[str | None, Depends(get_client_ip)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> HTMLResponse:
    try:
        register_use_case.register(
            email=email,
            plain_password=password,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except DocuvectorError as err:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": str(err), "success": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return templates.TemplateResponse(
        request,
        "register.html",
        {"error": None, "success": "Cadastro recebido. Você já pode fazer login."},
    )


@router.get("/logout", response_model=None)
def logout() -> RedirectResponse:
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect


# =============================================================
# Chat principal (layout unificado: sidebar docs + área chat)
# =============================================================
@router.get("/app/chat", response_class=HTMLResponse)
def chat_page(
    request: Request,
    token_payload: CurrentTokenDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
    settings: SettingsDependency,
) -> HTMLResponse:
    """Página principal. Sidebar com documentos; área direita com chat."""
    documents = crud_use_case.list_for_owner(owner_id=token_payload.user_id)
    embedding_providers = [p.value for p in list_embedding_providers(settings)]
    llm_providers = [p.value for p in list_llm_providers_for_env(settings)]
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "user": token_payload,
            "documents": documents,
            "embedding_providers": embedding_providers,
            "llm_providers": llm_providers,
            "default_llm": settings.llm_default_provider.value,
            "active_page": "chat",
        },
    )


@router.post("/app/chat/ask", response_class=HTMLResponse)
def chat_ask(
    request: Request,
    token_payload: CurrentTokenDependency,
    answer_use_case: AnswerUseCaseDependency,
    client_ip: ClientIpDependency,
    query: Annotated[str, Form()],
    embedding_provider: Annotated[str, Form()],
    llm_provider: Annotated[str, Form()],
) -> HTMLResponse:
    """Responde e retorna um bloco de mensagem para o histórico (beforeend)."""
    provider_name = LlmProviderName(llm_provider)
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    llm_client = resolve_llm_client(provider_name)

    try:
        answer = answer_use_case.ask(
            AskInput(
                owner_id=token_payload.user_id,
                query=query,
                embedding_provider=embedder,
                llm_provider=provider_name,
                client_ip=client_ip,
                user_agent=request.headers.get("user-agent"),
            ),
            llm_client=llm_client,
        )
    except DocuvectorError as err:
        return templates.TemplateResponse(
            request,
            "partials/chat_message.html",
            {"query": query, "answer": None, "error": str(err)},
        )

    return templates.TemplateResponse(
        request,
        "partials/chat_message.html",
        {"query": query, "answer": answer, "error": None},
    )


@router.post("/app/chat/upload", response_class=HTMLResponse)
async def chat_upload(
    request: Request,
    token_payload: CurrentTokenDependency,
    ingestion_use_case: IngestionUseCaseDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
    client_ip: ClientIpDependency,
    file: UploadFile,
    embedding_provider: Annotated[str, Form()],
) -> HTMLResponse:
    """Upload inline na sidebar. Retorna lista atualizada de documentos."""
    raw_bytes = await file.read()
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    error_message: str | None = None
    try:
        ingestion_use_case.ingest(
            owner_id=token_payload.user_id,
            filename=file.filename or "documento",
            content=raw_bytes,
            embedding_provider=embedder,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except DocuvectorError as err:
        error_message = str(err)

    documents = crud_use_case.list_for_owner(owner_id=token_payload.user_id)
    return templates.TemplateResponse(
        request,
        "partials/sidebar_docs.html",
        {"documents": documents, "error": error_message},
    )


@router.post("/app/chat/delete/{document_id}", response_class=HTMLResponse)
def chat_delete_doc(
    request: Request,
    document_id: UUID,
    token_payload: CurrentTokenDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
    client_ip: ClientIpDependency,
) -> HTMLResponse:
    """Remove documento e atualiza a sidebar."""
    with suppress(ResourceNotFoundError):
        crud_use_case.delete_for_owner(
            owner_id=token_payload.user_id,
            document_id=document_id,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    documents = crud_use_case.list_for_owner(owner_id=token_payload.user_id)
    return templates.TemplateResponse(
        request,
        "partials/sidebar_docs.html",
        {"documents": documents, "error": None},
    )


# =============================================================
# Dashboard de métricas
# =============================================================
@router.get("/app/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    token_payload: CurrentTokenDependency,
    metrics_use_case: MetricsUseCaseDependency,
) -> HTMLResponse:
    metrics = metrics_use_case.get_dashboard(owner_id=token_payload.user_id)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": token_payload, "metrics": metrics, "active_page": "dashboard"},
    )


# =============================================================
# Benchmark de compressão (sidebar do chat)
# =============================================================
@router.post("/app/chat/compress/{document_id}", response_class=HTMLResponse)
def chat_compress_document(
    request: Request,
    document_id: UUID,
    token_payload: CurrentTokenDependency,
    compression_use_case: CompressionBenchmarkUseCaseDependency,
) -> HTMLResponse:
    """Roda benchmark de compressão e retorna resultado inline na sidebar."""
    try:
        results = compression_use_case.run(
            BenchmarkInput(
                owner_id=token_payload.user_id,
                document_id=document_id,
            )
        )
    except DocuvectorError as err:
        return templates.TemplateResponse(
            request,
            "partials/compression_result.html",
            {"results": None, "error": str(err), "document_id": document_id},
        )

    return templates.TemplateResponse(
        request,
        "partials/compression_result.html",
        {"results": results, "error": None, "document_id": document_id},
    )


# =============================================================
# Benchmark de embedding (dashboard)
# =============================================================
@router.post("/app/dashboard/benchmark-embedders", response_class=HTMLResponse)
def dashboard_benchmark_embedders(
    request: Request,
    token_payload: CurrentTokenDependency,
    embedding_benchmark_use_case: EmbeddingBenchmarkUseCaseDependency,
    query: Annotated[str, Form()],
) -> HTMLResponse:
    """Compara latência e custo entre providers de embedding."""
    try:
        result = embedding_benchmark_use_case.run(
            query=query,
            owner_id=token_payload.user_id,
        )
    except DocuvectorError as err:
        return templates.TemplateResponse(
            request,
            "partials/embedding_benchmark_result.html",
            {"result": None, "error": str(err)},
        )

    return templates.TemplateResponse(
        request,
        "partials/embedding_benchmark_result.html",
        {"result": result, "error": None},
    )


# =============================================================
# Admin — protegido: apenas role=admin
# =============================================================
@router.get("/app/admin", response_class=HTMLResponse, response_model=None)
def admin_page(
    request: Request,
    token_payload: CurrentTokenDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
) -> HTMLResponse | RedirectResponse:
    """Painel administrativo: lista de usuários e gestão de roles."""
    if token_payload.role is not UserRole.ADMIN:
        return RedirectResponse(url="/app/chat", status_code=status.HTTP_303_SEE_OTHER)

    page = admin_use_case.list_users(limit=100, offset=0)
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": token_payload,
            "users": page.items,
            "total_users": page.total,
            "roles": [r.value for r in UserRole],
            "active_page": "admin",
        },
    )


@router.post("/app/admin/users/{user_id}/delete", response_class=HTMLResponse)
def admin_delete_user(
    request: Request,
    user_id: UUID,
    token_payload: CurrentTokenDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
    client_ip: ClientIpDependency,
) -> HTMLResponse:
    """Remove usuário e retorna lista atualizada."""
    if token_payload.role is not UserRole.ADMIN:
        return templates.TemplateResponse(
            request,
            "partials/admin_user_list.html",
            {"users": [], "error": "Acesso negado.", "roles": []},
        )
    error_message: str | None = None

    try:
        admin_use_case.delete_user(
            acting_admin_id=token_payload.user_id,
            target_user_id=user_id,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except DocuvectorError as err:
        error_message = str(err)
    page = admin_use_case.list_users(limit=100, offset=0)
    return templates.TemplateResponse(
        request,
        "partials/admin_user_list.html",
        {
            "users": page.items,
            "roles": [r.value for r in UserRole],
            "error": error_message,
            "admin_id": token_payload.user_id,
        },
    )


@router.post("/app/admin/users/{user_id}/role", response_class=HTMLResponse)
def admin_change_role(
    request: Request,
    user_id: UUID,
    token_payload: CurrentTokenDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
    client_ip: ClientIpDependency,
    role: Annotated[str, Form()],
) -> HTMLResponse:
    """Troca role do usuário e retorna lista atualizada."""
    if token_payload.role is not UserRole.ADMIN:
        return templates.TemplateResponse(
            request,
            "partials/admin_user_list.html",
            {"users": [], "error": "Acesso negado.", "roles": []},
        )

    error_message: str | None = None

    try:
        admin_use_case.change_role(
            acting_admin_id=token_payload.user_id,
            target_user_id=user_id,
            new_role=UserRole(role),
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except DocuvectorError as err:
        error_message = str(err)
    page = admin_use_case.list_users(limit=100, offset=0)
    return templates.TemplateResponse(
        request,
        "partials/admin_user_list.html",
        {
            "users": page.items,
            "roles": [r.value for r in UserRole],
            "error": error_message,
            "admin_id": token_payload.user_id,
        },
    )


@router.post("/app/admin/users/create", response_class=HTMLResponse)
def admin_create_user(
    request: Request,
    token_payload: CurrentTokenDependency,
    admin_use_case: AdminUserManagementUseCaseDependency,
    client_ip: ClientIpDependency,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()],
) -> HTMLResponse:
    """Cria usuário via painel admin e retorna lista atualizada."""
    if token_payload.role is not UserRole.ADMIN:
        return templates.TemplateResponse(
            request,
            "partials/admin_user_list.html",
            {"users": [], "error": "Acesso negado.", "roles": []},
        )

    error_message: str | None = None

    try:
        admin_use_case.create_user(
            acting_admin_id=token_payload.user_id,
            email=email,
            plain_password=password,
            role=UserRole(role),
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except DocuvectorError as err:
        error_message = str(err)

    page = admin_use_case.list_users(limit=100, offset=0)

    return templates.TemplateResponse(
        request,
        "partials/admin_user_list.html",
        {
            "users": page.items,
            "roles": [r.value for r in UserRole],
            "error": error_message,
            "admin_id": token_payload.user_id,
        },
    )
