# Patch para Limiter compartilhado — gap #1 da auditoria

## Diagnóstico

Hoje existem **dois** `Limiter` no projeto:

- `src/docuvector/api/routers/auth.py`: `limiter = Limiter(key_func=...)`
- `src/docuvector/api/routers/queries.py`: `limiter = Limiter(key_func=...)`

E o `main.py` registra apenas o do `auth_router` em `app.state.limiter`:

```python
fastapi_app.state.limiter = auth_router.limiter
```

Consequência: o slowapi consulta `app.state.limiter` para coordenar
storage de rate-limit. Com duas instâncias, ou o `/queries/ask` não
limita de fato (porque o decorador usa instância sem registro), ou
limita usando contadores separados de `/auth/*`. Comportamento
inconsistente, difícil de diagnosticar.

## Correção

Substituir as duas instâncias por **uma única** declarada em
`src/docuvector/api/limiting.py` (fornecido neste patch). Em cada
router, importar `shared_limiter` e usá-lo no decorador. Em `main.py`,
registrar `shared_limiter` (não `auth_router.limiter`).

## Arquivos a editar

### 1. `src/docuvector/api/routers/auth.py`

**Remover:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
...
limiter = Limiter(key_func=get_remote_address)
```

**Adicionar:**
```python
from docuvector.api.limiting import shared_limiter
```

**Trocar** decoradores `@limiter.limit(...)` por `@shared_limiter.limit(...)`.

### 2. `src/docuvector/api/routers/queries.py`

Mesma operação: remover criação local de `Limiter`, importar `shared_limiter`,
trocar decoradores.

### 3. `src/docuvector/main.py`

**Trocar:**
```python
fastapi_app.state.limiter = auth_router.limiter
```

**Por:**
```python
from docuvector.api.limiting import shared_limiter

fastapi_app.state.limiter = shared_limiter
```

## Validação

```bash
## Confere que só sobrou UMA instância de Limiter no projeto:
grep -rn "Limiter(" src/docuvector/
## Esperado: APENAS src/docuvector/api/limiting.py:shared_limiter = Limiter(...)
```

```bash
## Confere que o registro no main aponta para a instância compartilhada:
grep "state.limiter" src/docuvector/main.py
## Esperado: fastapi_app.state.limiter = shared_limiter
```

## Por quê este patch é separado

Esse gap é **pré-existente** no projeto (vem desde antes do Bloco 5).
Por isso vai como patch opcional, não como parte obrigatória do bloco
LLM-pluggable. Mas é um risco real de produção e vale corrigir antes
da banca.
