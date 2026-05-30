"""Entidade de evento de auditoria (ledger imutável).

Decisão arquitetural: `audit_logs` é um LEDGER de eventos forenses,
NÃO um apêndice da tabela de usuários. Consequências de design:

1.  `actor_user_id` é apenas um UUID de contexto, SEM foreign key para
    `users.id`. Quando um usuário é deletado, os eventos preservam a
    referência histórica.

2.  Snapshots de contexto (`actor_email`, `actor_role`) viajam dentro
    do evento. O leitor do ledger não depende de JOIN com `users`
    para entender quem fez o quê. Importante porque:
    - O email do usuário pode mudar depois do evento (compliance/LGPD).
    - O usuário pode ter sido deletado, e o evento ainda precisa ser
      legível (NIST SP 800-53 AU-2: registros sobrevivem a mudanças
      no estado dos atores).
    - O papel pode ter sido alterado (promoção/rebaixamento).

3.  `correlation_id` permite agrupar eventos de uma mesma requisição
    HTTP ou job batch. Útil para trilha forense de fluxos compostos
    (ex.: upload que dispara ingestão + audit múltiplo).

4.  Frozen + slots: eventos NÃO podem ser modificados após criação.
    Append-only por construção da própria entidade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from docuvector.domain.enums import AuditAction, AuditStatus, UserRole


def _utc_now() -> datetime:
    """Timestamp timezone-aware em UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Registro forense imutável de uma ação sensível.

    A identidade do ator é capturada por snapshot: `actor_user_id` é o
    UUID histórico, e `actor_email` / `actor_role` retratam o estado
    do usuário no momento exato do evento.
    """

    action: AuditAction
    status: AuditStatus
    resource_type: str
    id: UUID = field(default_factory=uuid4)

    # Identidade histórica do ator (sem FK; pode apontar para user deletado)
    actor_user_id: UUID | None = None
    actor_email: str | None = None
    actor_role: UserRole | None = None

    # Recurso alvo da operação
    resource_id: UUID | None = None

    # Contexto de rede
    ip_address: str | None = None
    user_agent: str | None = None

    # Tracing entre eventos da mesma operação
    correlation_id: UUID | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
