"""Contrato de repositório de eventos de auditoria."""

from __future__ import annotations

from typing import Protocol

from docuvector.domain.entities import AuditEvent


class AuditRepository(Protocol):
    """Persistência de eventos de auditoria.

    Auditoria é append-only por design; não há delete nem update.
    """

    def append(self, event: AuditEvent) -> None:
        """Registra um novo evento de auditoria."""
        ...

    def list_paginated(self, offset: int, limit: int) -> list[AuditEvent]:
        """Lista eventos em ordem cronológica decrescente (mais recentes primeiro).

        Apenas administradores acessam o painel que consome este método.
        Validação de papel é responsabilidade da camada de apresentação.
        """
        ...
