"""Camada web (server-side rendering) do DocuVector Lite.

Separada dos routers de API REST. Renderiza HTML via Jinja2 + HTMX,
consumindo a mesma lógica de domínio através dos use cases.

A autenticação usa cookie HttpOnly (ver SESSION_COOKIE_NAME em deps.py),
mantendo o JWT fora do alcance do JavaScript.
"""

from docuvector.api.web.router import router

__all__ = ["router"]
