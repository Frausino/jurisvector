# Users Management V2 — Gaps de Segurança Fechados

Versão consolidada do pacote `users-management` com os 9 gaps
identificados pela revisão técnica corrigidos.

## Gaps fechados

| # | Gap | Solução |
|---|-----|---------|
| 1 | Lint RUF100 + F401 + PLR2004 | Constantes nomeadas; `noqa` redundantes removidos |
| 2 | Testes blocklist com senhas curtas | Separa gate de comprimento da blocklist; usa senhas >= 12 chars na lista |
| 3 | **`/register` vaza por 409 e por timing** | `RegistrationAcknowledgement` genérico 201 em ambos os caminhos; hash dummy no caminho duplicado; floor de latência configurável (default 0.6s > bcrypt cost 12) |
| 4 | **OOM no upload (read antes do check)** | Leitura em chunks de 1 MB com aborto early no excesso |
| 5 | **Check email-na-senha morto** | Interface `validate(password, owner_identifier=None)`; use cases passam email |
| 6 | **bcrypt trunca em 72 bytes** | Migra para `bcrypt_sha256` (pré-hash SHA-256) |
| 7 | **IP forjável + rate limit atrás de proxy** | Settings `TRUSTED_PROXY_IPS`; headers só aceitos de peers confiáveis |
| 8 | Blocklist sombreada pelo length gate | Lista refeita com 97 entradas, todas >= 12 chars |
| 9 | Duplicação min_length (hasher vs policy) | Removido do hasher; única fonte de verdade é o validator |

## Estrutura

```
users-mgmt-v2/
├── .env.example                                              [SUBSTITUI]
├── src/docuvector/
│   ├── config/
│   │   └── settings.py                                       [SUBSTITUI]
│   │       (+ TRUSTED_PROXY_IPS, REGISTER_MIN_LATENCY_SECONDS)
│   ├── domain/
│   │   ├── enums.py                                          [SUBSTITUI]
│   │   └── interfaces/
│   │       ├── __init__.py                                   [SUBSTITUI]
│   │       ├── password_policy_validator.py                  [NOVO/REFAT]
│   │       │   (validate recebe owner_identifier)
│   │       └── user_repository.py                            [SUBSTITUI]
│   ├── infrastructure/
│   │   ├── persistence/
│   │   │   └── user_repository_impl.py                       [SUBSTITUI]
│   │   └── security/
│   │       ├── bcrypt_hasher.py                              [SUBSTITUI]
│   │       │   (bcrypt_sha256, sem MIN_PASSWORD_LENGTH local)
│   │       ├── common_passwords.txt                          [NOVO]
│   │       │   (97 entradas, todas >= 12 chars)
│   │       └── nist_password_policy_validator.py             [NOVO/REFAT]
│   │           (stateless, owner_identifier por chamada)
│   ├── application/
│   │   ├── register_user_use_case.py                         [NOVO/REFAT]
│   │   │   (anti-enum: never raises duplicate, dummy hash)
│   │   └── admin_user_management_use_case.py                 [NOVO]
│   ├── api/
│   │   ├── deps.py                                           [SUBSTITUI]
│   │   │   (get_client_ip valida TRUSTED_PROXY_IPS)
│   │   ├── routers/
│   │   │   ├── auth.py                                       [SUBSTITUI]
│   │   │   │   (/register sempre 201, latency floor do Settings)
│   │   │   ├── admin_users.py                                [NOVO]
│   │   │   └── documents.py                                  [SUBSTITUI]
│   │   │       (upload streaming chunked, anti-OOM)
│   │   └── schemas/
│   │       └── auth.py                                       [SUBSTITUI]
│   │           (RegistrationAcknowledgement genérico)
│   └── main.py                                               [SUBSTITUI]
├── scripts/
│   └── seed_admin.py                                         [NOVO]
└── tests/
    ├── conftest.py                                           [SUBSTITUI]
    ├── unit/
    │   ├── application/
    │   │   ├── test_register_user_use_case.py                [NOVO]
    │   │   │   (cobre anti-enum + hash dummy + identifier)
    │   │   └── test_admin_user_management_use_case.py        [NOVO]
    │   └── infrastructure/
    │       └── test_password_policy.py                       [NOVO]
    │           (gates separados: length / blocklist / identifier)
    └── integration/
        └── test_register_and_admin.py                        [NOVO]
            (verifica duplicado retorna 201; senha original intacta)
```

## Como aplicar

```powershell
git checkout feature/sprint-3-rag-domain
# (opcional) cria branch dedicada:
# git checkout -b feature/user-management-v2

Expand-Archive -Path .\users-mgmt-v2.zip -DestinationPath . -Force

# Atualiza .env (remove SEED_USER1/2; ajusta os defaults novos)
notepad .env

# Deleta script antigo (já substituído)
Remove-Item scripts/seed_users.py -ErrorAction SilentlyContinue

# Roda gates
just sync
just lint
just format-check
just type
just test-unit
just up
just migrate
just seed-admin
just test-integration
just ci
```

## Atualizar `.env` real (mínimo)

REMOVE:
```
SEED_USER1_*
SEED_USER2_*
```

ADICIONA / GARANTE:
```
SEED_ADMIN_EMAIL=admin@docuvector.local
SEED_ADMIN_PASSWORD=<senha-forte-12-chars-fora-blocklist>
PASSWORD_MIN_LENGTH=12
REGISTER_RATE_LIMIT_PER_MINUTE=5
REGISTER_MIN_LATENCY_SECONDS=0.6
TRUSTED_PROXY_IPS=
```

## Atualizar `pyproject.toml` e `justfile`

`pyproject.toml`:
```toml
[project.scripts]
seed-admin = "scripts.seed_admin:main"
```

`justfile`:
```just
seed-admin:
    uv run python -m scripts.seed_admin
```

## Migração de hashes existentes (bcrypt → bcrypt_sha256)

**Importante:** o hash do admin seedado anteriormente foi gerado com
`bcrypt` puro. Após esta atualização, a verificação via
`bcrypt_sha256.verify()` levanta `UnknownHashError` para esses hashes.

Duas opções:

1.  **Reset do banco (recomendado em dev/test):**
    ```powershell
    just down-clean
    just up
    just migrate
    just seed-admin
    ```
    Cria admin novo com hash bcrypt_sha256.

2.  **Migração in-place (se houver users criados):** adicionar
    `bcrypt` ao `CryptContext` como esquema deprecated mantém retro-
    compatibilidade até o próximo login (passlib re-hashea). Para
    isso, alterar `bcrypt_hasher.py`:
    ```python
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated=["bcrypt"],
    bcrypt_sha256__rounds=rounds,
    bcrypt__rounds=rounds,
    ```
    Trade-off: superfície de schemes maior, mas zero downtime.

Em ambiente acadêmico/TCC, reset é mais limpo.

## Frases para a banca (gaps virando defesa)

> "O endpoint /register implementa defesa em três camadas contra
> enumeração de e-mails: rate limit por IP, latência mínima
> configurável acima do tempo de bcrypt cost 12, e resposta HTTP
> idêntica para criação real ou e-mail já cadastrado. O atacante não
> distingue os caminhos nem pelo corpo, nem pelo status, nem pelo
> timing. Audit log preserva a distinção para análise forense."

> "Migrei de bcrypt puro para bcrypt_sha256, recomendação OWASP para
> senhas longas. O bcrypt original trunca silenciosamente em 72 bytes,
> e passphrases UTF-8 com acentos batem nesse limite. O pré-hash
> SHA-256 evita colisões em senhas que coincidem nos primeiros 72
> bytes."

> "X-Forwarded-For só é confiável quando a requisição vem de um
> reverse proxy que o operador declarou em TRUSTED_PROXY_IPS. Sem essa
> allowlist, um cliente forja IP no log de auditoria. A política está
> no Settings, não no código: deploys atrás de NGINX configuram os
> IPs do balanceador; deploys em localhost ficam com a lista vazia e
> usam o peer TCP direto."

## DoD

- [ ] `just type` verde
- [ ] `just lint` verde (0 RUF100, 0 PLR2004)
- [ ] `just test-unit` verde (cobertura ≥ 80% em policy + register)
- [ ] `just test-integration` verde (duplicate retorna 201)
- [ ] `just seed-admin` cria admin idempotente
- [ ] Hash do admin no banco começa com `$bcrypt-sha256$`
- [ ] `/register` com email novo retorna 201 (sem id/email no body)
- [ ] `/register` com email duplicado retorna 201 com mesma resposta
- [ ] Login com senha "atacante" no email duplicado retorna 401
- [ ] Upload de arquivo > 10MB retorna 413 sem OOM
- [ ] `/admin/users` sem admin token retorna 403

## Commit sugerido

```powershell
git add -A
git commit -m "feat(security): close 9 gaps - anti-enum, bcrypt_sha256, ip spoofing, oom"
git push
```
