"""Enumerações de domínio compartilhadas entre entidades."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """Papéis de autorização do sistema."""

    ADMIN = "admin"
    USER = "user"


class AuditAction(str, Enum):
    """Ações sensíveis registradas no log de auditoria.

    Centralizar como enum evita strings mágicas espalhadas pelo código
    e facilita correlação entre eventos no painel administrativo.
    """

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    USER_SEEDED = "user_seeded"
    ACCESS_DENIED = "access_denied"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_UPDATED = "document_updated"
    QUERY_EXECUTED = "query_executed"


class AuditStatus(str, Enum):
    """Resultado de uma ação auditada.

    `forbidden` diferencia tentativas de acesso indevido (que retornam
    HTTP 404 ao cliente para mascarar existência) de falhas legítimas.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    FORBIDDEN = "forbidden"
