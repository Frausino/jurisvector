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
    AuthUseCaseDependency,
    ClientIpDependency,
    CompareRetrievalUseCaseDependency,
    CompressionBenchmarkUseCaseDependency,
    CurrentTokenDependency,
    DocumentCrudUseCaseDependency,
    EmbeddingBenchmarkUseCaseDependency,
    MetricsUseCaseDependency,
    RegisterUserUseCaseDependency,
    SessionDependency,
    SettingsDependency,
    build_answer_use_case_for_store,
    get_client_ip,
    provide_compress_to_collection_use_case,
    provide_ingestion_use_case_for_provider,
    resolve_vector_store_by_collection,
)
from docuvector.api.web.templating import current_user_or_none, templates
from docuvector.application.answer_use_case import AskInput
from docuvector.application.compress_to_collection_use_case import (
    CompressToCollectionInput,
)
from docuvector.application.compression_benchmark_use_case import BenchmarkInput
from docuvector.config.settings import get_settings
from docuvector.domain.enums import (
    CompressionMethod,
    EmbeddingProviderName,
    LlmProviderName,
    UserRole,
)
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
    client_ip: ClientIpDependency,
    settings: SettingsDependency,
    query: Annotated[str, Form()],
    embedding_provider: Annotated[str, Form()],
    llm_provider: Annotated[str, Form()],
    vector_collection: Annotated[str, Form()] = "original",
) -> HTMLResponse:
    """RAG na coleção escolhida (original, int8, binary, rp, pca).

    O VectorStore é resolvido por request a partir do nome da coleção,
    sem alterar singletons globais. Padrão Strategy.
    """
    provider_name = LlmProviderName(llm_provider)
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    llm_client = resolve_llm_client(provider_name)

    # Resolve o store considerando o provider de embedding.
    # ST (384 dims) e OpenAI (1536 dims) usam coleções Chroma distintas.
    store = resolve_vector_store_by_collection(
        collection=vector_collection,
        embedding_provider=embedding_provider,
    )
    answer_use_case = build_answer_use_case_for_store(store)

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
            {"query": query, "answer": None, "error": str(err), "collection": vector_collection},
        )

    return templates.TemplateResponse(
        request,
        "partials/chat_message.html",
        {"query": query, "answer": answer, "error": None, "collection": vector_collection},
    )


@router.post("/app/chat/upload", response_class=HTMLResponse)
async def chat_upload(
    request: Request,
    token_payload: CurrentTokenDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
    client_ip: ClientIpDependency,
    session: SessionDependency,
    file: UploadFile,
    embedding_provider: Annotated[str, Form()],
) -> HTMLResponse:
    """Upload com roteamento automatico de colecao por embedding provider.

    ST (sentence_transformers) -> colecoes docuvector_* (384 dims)
    OpenAI -> colecoes docuvector_oai_* (1536 dims)
    Evita InvalidDimensionException do ChromaDB.
    """
    raw_bytes = await file.read()
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    ingestion_use_case = provide_ingestion_use_case_for_provider(
        session=session,
        embedding_provider_name=embedding_provider,
    )
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
# POST /app/chat/compare — comparação de retrieval entre coleções
# =============================================================
@router.post("/app/chat/compare", response_class=HTMLResponse)
def chat_compare_retrieval(
    request: Request,
    token_payload: CurrentTokenDependency,
    compare_use_case: CompareRetrievalUseCaseDependency,
    query: Annotated[str, Form()],
    embedding_provider: Annotated[str, Form()],
) -> HTMLResponse:
    """Roda a query nas 5 coleções (original + 4 comprimidas) e retorna
    tabela comparativa com Recall@K, Precision@K e MRR.

    Expõe empiricamente a resposta a: "A compressão degrada o retrieval?"
    """
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    try:
        result = compare_use_case.compare(
            owner_id=token_payload.user_id,
            query=query,
            embedding_provider=embedder,
        )
    except DocuvectorError as compare_error:
        return templates.TemplateResponse(
            request,
            "partials/compare_result.html",
            {"result": None, "error": str(compare_error)},
        )

    return templates.TemplateResponse(
        request,
        "partials/compare_result.html",
        {"result": result, "error": None},
    )


# =============================================================
# Dashboard de métricas
# =============================================================
@router.get("/app/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    token_payload: CurrentTokenDependency,
    metrics_use_case: MetricsUseCaseDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
    settings: SettingsDependency,
) -> HTMLResponse:
    metrics = metrics_use_case.get_dashboard(owner_id=token_payload.user_id)
    documents = crud_use_case.list_for_owner(owner_id=token_payload.user_id)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": token_payload,
            "metrics": metrics,
            "documents": documents,
            "active_page": "dashboard",
            "embedding_providers": [p.value for p in list_embedding_providers(settings)],
            "llm_providers": [p.value for p in list_llm_providers_for_env(settings)],
        },
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
# POST /app/chat/compress-to/{document_id}/{method}
# Comprime e PERSISTE na coleção Chroma alvo (não só benchmark)
# =============================================================
@router.post(
    "/app/chat/compress-to/{document_id}/{method}",
    response_class=HTMLResponse,
)
def chat_compress_to_collection(
    request: Request,
    document_id: UUID,
    method: str,
    token_payload: CurrentTokenDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
    embedding_provider: Annotated[str, Form()] = "sentence_transformers",
) -> HTMLResponse:
    """Comprime e indexa o documento na coleção Chroma do método escolhido.

    Diferente do /compress/{id} (benchmark), esta rota persiste os vetores
    comprimidos, tornando a coleção disponível para retrieval no chat.
    """
    try:
        cm = CompressionMethod(method)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/compress_to_result.html",
            {"result": None, "error": f"Método inválido: {method}", "document_id": document_id},
        )

    use_case = provide_compress_to_collection_use_case(
        method_name=method,
        embedding_provider=embedding_provider,
    )

    # Recupera o filename do documento (BOLA: filtra por owner_id)
    documents = crud_use_case.list_for_owner(owner_id=token_payload.user_id)
    doc = next((d for d in documents if d.id == document_id), None)
    if doc is None:
        return templates.TemplateResponse(
            request,
            "partials/compress_to_result.html",
            {"result": None, "error": "Documento não encontrado.", "document_id": document_id},
        )

    try:
        result = use_case.compress(
            CompressToCollectionInput(
                owner_id=token_payload.user_id,
                document_id=document_id,
                document_filename=doc.filename,
                compression_method=cm,
            )
        )
    except DocuvectorError as err:
        return templates.TemplateResponse(
            request,
            "partials/compress_to_result.html",
            {"result": None, "error": str(err), "document_id": document_id},
        )

    return templates.TemplateResponse(
        request,
        "partials/compress_to_result.html",
        {"result": result, "error": None, "document_id": document_id},
    )


# =============================================================
# POST /app/chat/compare-answer
# Comparação A/B de resposta entre duas coleções
# =============================================================
@router.post("/app/chat/compare-answer", response_class=HTMLResponse)
def chat_compare_answer(
    request: Request,
    token_payload: CurrentTokenDependency,
    client_ip: ClientIpDependency,
    settings: SettingsDependency,
    query: Annotated[str, Form()],
    embedding_provider: Annotated[str, Form()],
    llm_provider: Annotated[str, Form()],
    collection_a: Annotated[str, Form()] = "original",
    collection_b: Annotated[str, Form()] = "int8",
) -> HTMLResponse:
    """Roda a mesma query em duas coleções e retorna respostas lado a lado.

    Permite comparar empiricamente se a compressão afeta a qualidade
    da resposta gerada — não apenas as métricas de retrieval.
    """
    provider_name = LlmProviderName(llm_provider)
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    llm_client = resolve_llm_client(provider_name)

    def _run_ask(collection: str) -> tuple[object | None, str | None]:
        store = resolve_vector_store_by_collection(
            collection=collection,
            embedding_provider=embedding_provider,
        )
        uc = build_answer_use_case_for_store(store)
        try:
            return uc.ask(
                AskInput(
                    owner_id=token_payload.user_id,
                    query=query,
                    embedding_provider=embedder,
                    llm_provider=provider_name,
                    client_ip=client_ip,
                    user_agent=request.headers.get("user-agent"),
                ),
                llm_client=llm_client,
            ), None
        except DocuvectorError as err:
            return None, str(err)

    answer_a, error_a = _run_ask(collection_a)
    answer_b, error_b = _run_ask(collection_b)

    return templates.TemplateResponse(
        request,
        "partials/compare_answer.html",
        {
            "query": query,
            "collection_a": collection_a,
            "collection_b": collection_b,
            "answer_a": answer_a,
            "error_a": error_a,
            "answer_b": answer_b,
            "error_b": error_b,
        },
    )


# =============================================================
# Dashboard: rotas que estavam faltando (eram 404)
# =============================================================
@router.get("/app/dashboard/corpus-docs", response_class=HTMLResponse)
def dashboard_corpus_docs(
    request: Request,
    token_payload: CurrentTokenDependency,
    crud_use_case: DocumentCrudUseCaseDependency,
) -> HTMLResponse:
    documents = crud_use_case.list_for_owner(owner_id=token_payload.user_id)
    return templates.TemplateResponse(
        request,
        "partials/corpus_docs_table.html",
        {"documents": documents},
    )


@router.post("/app/dashboard/compare-retrieval", response_class=HTMLResponse)
def dashboard_compare_retrieval(
    request: Request,
    token_payload: CurrentTokenDependency,
    compare_use_case: CompareRetrievalUseCaseDependency,
    query: Annotated[str, Form()],
    embedding_provider: Annotated[str, Form()],
) -> HTMLResponse:
    embedder = resolve_embedder(EmbeddingProviderName(embedding_provider))
    try:
        result = compare_use_case.compare(
            owner_id=token_payload.user_id,
            query=query,
            embedding_provider=embedder,
        )
    except DocuvectorError as err:
        return templates.TemplateResponse(
            request,
            "partials/compare_result.html",
            {"result": None, "error": str(err)},
        )
    return templates.TemplateResponse(
        request,
        "partials/compare_result.html",
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
    with suppress(DocuvectorError):
        admin_use_case.delete_user(
            acting_admin_id=token_payload.user_id,
            target_user_id=user_id,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    page = admin_use_case.list_users(limit=100, offset=0)
    return templates.TemplateResponse(
        request,
        "partials/admin_user_list.html",
        {
            "users": page.items,
            "roles": [r.value for r in UserRole],
            "error": None,
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
    with suppress(DocuvectorError):
        admin_use_case.change_role(
            acting_admin_id=token_payload.user_id,
            target_user_id=user_id,
            new_role=UserRole(role),
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    page = admin_use_case.list_users(limit=100, offset=0)
    return templates.TemplateResponse(
        request,
        "partials/admin_user_list.html",
        {
            "users": page.items,
            "roles": [r.value for r in UserRole],
            "error": None,
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
    with suppress(DocuvectorError):
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
