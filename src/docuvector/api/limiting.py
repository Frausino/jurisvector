"""Limiter compartilhado entre routers (slowapi).

Existe UMA instância de `Limiter` no processo. `main.py` registra
essa instância em `app.state.limiter`, e cada router usa o mesmo
objeto para o decorador `@limiter.limit(...)`. Isso garante que o
storage de rate-limit é único, evitando a inconsistência de ter
routers com `Limiter` próprio que não estão registrados no app.state.

Por que não usar `slowapi.extension.Limiter` global:
- A criação precoce do `Limiter` precisa acontecer no import time
  dos routers (porque o decorador @limiter.limit é avaliado nesse
  momento). Concentrar a instância aqui é mais explícito que
  espalhar `Limiter(...)` em cada router.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Instância única do Limiter de toda a aplicação. Routers importam
# `shared_limiter` e usam `@shared_limiter.limit("...")`. O `main.py`
# registra essa instância em `app.state.limiter` no boot.
shared_limiter: Limiter = Limiter(key_func=get_remote_address)
