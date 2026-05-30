# Users Management — Registro Público + Admin CRUD

Pacote que substitui o modelo "seed estático de 3 contas" por
arquitetura de produção:

- **1 admin** seedado via `.env` no bootstrap (SEED_ADMIN_*)
- **N usuários** criados via `POST /api/v1/auth/register` (público)
- **Admin CRUD completo** via `/api/v1/admin/users/*`

## Estrutura

```
users-management/
├── src/docuvector/
│   ├── config/
│   │   └── settings.py                                  [SUBSTITUI]
│   ├── domain/
│   │   ├── enums.py                                     [SUBSTITUI] (4 audit actions novos)
│   │   └── interfaces/
│   │       ├── __init__.py                              [SUBSTITUI]
│   │       ├── password_policy_validator.py             [NOVO]
│   │       └── user_repository.py                       [SUBSTITUI] (list_all + count_all + delete_by_id)
│   ├── infrastructure/
│   │   ├── persistence/
│   │   │   └── user_repository_impl.py                  [SUBSTITUI]
│   │   └── security/
│   │       ├── common_passwords.txt                     [NOVO]
│   │       └── nist_password_policy_validator.py        [NOVO]
│   ├── application/
│   │   ├── register_user_use_case.py                    [NOVO]
│   │   └── admin_user_management_use_case.py            [NOVO]
│   ├── api/
│   │   ├── deps.py                                      [SUBSTITUI]
│   │   ├── routers/
│   │   │   ├── auth.py                                  [SUBSTITUI] (adiciona /register)
│   │   │   └── admin_users.py                           [NOVO]
│   │   └── schemas/
│   │       └── auth.py                                  [SUBSTITUI]
│   └── main.py                                          [SUBSTITUI] (registra admin_users + handler 409)
├── scripts/
│   └── seed_admin.py                                    [NOVO] (substitui seed_users.py)
└── tests/
    ├── conftest.py                                      [SUBSTITUI] (RGN-T1 — sem hardcoded)
    ├── unit/
    │   ├── application/
    │   │   ├── test_register_user_use_case.py           [NOVO]
    │   │   └── test_admin_user_management_use_case.py   [NOVO]
    │   └── infrastructure/
    │       └── test_password_policy.py                  [NOVO]
    └── integration/
        └── test_register_and_admin.py                   [NOVO]
```

## Pré-requisitos

Bloco 1 (CRUD docs), Bloco 2 (extractors) e Bloco 3 (embeddings+ingestion) já
aplicados. Este pacote substitui alguns arquivos desses blocos.

## Como aplicar

```powershell
git checkout feature/sprint-3-rag-domain
# ou cria branch própria:
git checkout -b feature/user-management

Expand-Archive -Path .\users-management.zip -DestinationPath . -Force

# Apaga o script antigo de seed (substituído por seed_admin.py).
Remove-Item scripts/seed_users.py -ErrorAction SilentlyContinue
```

## Atualizações necessárias no `.env`

REMOVE essas linhas:
```
SEED_USER1_EMAIL=...
SEED_USER1_PASSWORD=...
SEED_USER2_EMAIL=...
SEED_USER2_PASSWORD=...
```

ADICIONA (opcionalmente, para ajustar defaults):
```
PASSWORD_MIN_LENGTH=12
REGISTER_RATE_LIMIT_PER_MINUTE=5
```

Mantém o que já existe:
```
SEED_ADMIN_EMAIL=admin@docuvector.com
SEED_ADMIN_PASSWORD=<senha-forte-12+-chars>
```

## Atualização no `pyproject.toml`

Trocar:
```toml
[project.scripts]
seed-users = "docuvector.scripts.seed_users:main"
```

Por:
```toml
[project.scripts]
seed-admin = "scripts.seed_admin:main"
```

## Atualização no `justfile`

Substituir a receita `seed-users` por:
```
seed-admin:
    uv run python -m scripts.seed_admin
```

## Sequência de validação

```powershell
# 1. Gates estáticos
just lint
just format-check
just type

# 2. Banco
just up
just migrate

# 3. Bootstrap admin (idempotente)
just seed-admin
# Esperado log: seed_admin_created (primeira vez) ou seed_admin_already_exists

# 4. Testes
just test-unit
just test-integration
just ci

# 5. Smoke no Swagger
just dev

# No Swagger (http://127.0.0.1:8000/docs):
# a) POST /api/v1/auth/register   -> cria conta pública
# b) POST /api/v1/auth/login      -> pega token
# c) Authorize (cadeado)          -> cola token
# d) GET  /api/v1/auth/me         -> confere usuário atual

# Como admin:
# a) Login com SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD
# b) GET  /api/v1/admin/users     -> lista todos
# c) POST /api/v1/admin/users     -> cria com role=admin se quiser
# d) DELETE /api/v1/admin/users/{id} -> apaga
# e) PATCH /api/v1/admin/users/{id}/role -> promove/rebaixa
```

## Endpoints novos

| Método | Path                                    | Auth     | Descrição |
|--------|-----------------------------------------|----------|-----------|
| POST   | /api/v1/auth/register                   | Pública  | Auto-cadastro com NIST password policy |
| GET    | /api/v1/admin/users                     | Admin    | Lista paginada de usuários |
| POST   | /api/v1/admin/users                     | Admin    | Cria usuário com role arbitrária |
| DELETE | /api/v1/admin/users/{id}                | Admin    | Apaga usuário (não pode ser self) |
| PATCH  | /api/v1/admin/users/{id}/role           | Admin    | Promove/rebaixa (não pode rebaixar self) |

## Decisões arquiteturais embarcadas

1.  **Política de senha NIST SP 800-63B (2024).** 12 chars min, sem
    complexidade artificial, bloqueio de lista de vazadas, bloqueio
    de similaridade com email do usuário.

2.  **Rate limit + timing equalizer no /register.** 5 tentativas/min
    por IP (configurável) + piso de latência de 150ms ± 20ms de jitter
    para impedir oracle de enumeração de emails cadastrados.

3.  **Self-cadastro sempre cria `role=user`.** Promoção a admin é
    exclusiva do `PATCH /admin/users/{id}/role`. Nem via API pública
    nem via banco direto (CHECK constraint não aplicado mas validado
    no use case) o usuário pode se auto-promover.

4.  **Anti-bricking embarcado:**
    - Admin não pode deletar a si mesmo (`AuthorizationError`)
    - Admin não pode rebaixar a si mesmo (`AuthorizationError`)
    - Mudar para o mesmo papel é no-op idempotente

5.  **Apenas 1 conta seedada.** `SEED_USER1/2` removidos. O fluxo
    real do produto começa com `seed-admin` e tudo mais é dinâmico.

6.  **Audit log em TODAS as ações sensíveis.** 4 ações novas no enum:
    USER_REGISTERED, USER_CREATED_BY_ADMIN, USER_DELETED,
    USER_ROLE_CHANGED. Toda operação grava IP, user-agent, metadata
    relevante (email mudado, role anterior, etc.).

7.  **RGN-T1 aplicada nos testes novos.** Nenhuma senha hardcoded.
    `TEST_REGISTRATION_PASSWORD`, `TEST_WEAK_PASSWORD`, etc., todos
    via `os.environ.setdefault` no conftest.

8.  **Lista de senhas comuns embarcada (80 entradas).** Lookup O(1)
    via `frozenset`, carregada uma vez por processo via `lru_cache`.
    Pode crescer indefinidamente sem mudar código.

9.  **Email normalizado (lowercase) no use case, antes do banco.**
    Junto com CITEXT no Postgres (Sprint 2 Dia 4), garante dedup
    case-insensitive em todas as camadas.

## Frases para a banca

> "Sigo NIST SP 800-63B Rev. 4 de 2024: senha de pelo menos 12 caracteres,
> sem regra de complexidade artificial, com bloqueio contra lista local de
> senhas vazadas. NIST removeu a obrigação de complexidade porque pesquisa
> mostra que aquela regra de '1 maiúscula 1 número 1 símbolo' gera senhas
> previsíveis tipo 'Senha123!'."

> "O endpoint /register tem rate limit por IP e timing equalizer: latência
> mínima de 150ms com jitter aleatório. Sem isso, a diferença de tempo entre
> 'email já existe' e 'email novo' permitiria enumerar contas via timing."

> "Admin não pode deletar nem rebaixar a si mesmo. Caso contrário, em um
> sistema com 1 admin, um clique apaga todo o controle administrativo.
> A regra é validada no use case, não no banco — a fronteira do sistema
> aceita a tentativa e responde com 403."

## DoD

- [ ] `just type` verde
- [ ] `just lint` verde
- [ ] `just test-unit` verde (3 suítes novas, ~40 testes)
- [ ] `just test-integration` verde (1 suíte nova, ~12 testes)
- [ ] `just seed-admin` cria o admin na primeira execução
- [ ] `just seed-admin` é idempotente (segunda execução não duplica)
- [ ] Swagger mostra seção `admin` separada
- [ ] Self-cadastro cria role=user; promoção via admin

## Commit sugerido

```powershell
git add -A
git commit -m "feat(users): public registration + admin CRUD with NIST password policy"
git push
```
