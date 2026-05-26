# Estrutura inicial do repositório

Documento gerado na Sprint 1, Dia 2. Define a árvore canônica do projeto e como criá-la no Windows.

---

## 1. Árvore canônica

```
docuvector-lite/
├── .github/
│   └── workflows/
│       └── ci.yml                          # Sprint 1, Dia 3
├── docker/
│   ├── docker-compose.yml                  # entregue
│   └── postgres/
│       └── init.sql                        # entregue
├── docs/
│   ├── ESCOPO_CONGELADO.md                 # entregue (Dia 1)
│   ├── BRD.md                              # entregue (Dia 1)
│   ├── SRS.md                              # entregue (Dia 1)
│   ├── ARCHITECTURE.md                     # Sprint 8
│   ├── EVIDENCIAS.md                       # Sprint 8
│   ├── README_DEMO.md                      # Sprint 8
│   └── diagrams/
│       ├── use_case.puml                   # entregue (Dia 1)
│       ├── er.puml                         # entregue (Dia 1)
│       ├── class.puml                      # entregue (Dia 2)
│       ├── sequence_ingestion.puml         # entregue (Dia 2)
│       └── sequence_query.puml             # entregue (Dia 2)
├── data/                                   # criado vazio, ignorado pelo Git
│   ├── chroma/                             # persistência ChromaDB
│   └── hf_cache/                           # cache de modelos HuggingFace
├── migrations/                             # Alembic; gerado na Sprint 2
│   └── versions/
├── scripts/
│   └── seed_users.py                       # Sprint 2
├── src/
│   └── docuvector/
│       ├── __init__.py
│       ├── main.py                         # Sprint 1, Dia 3 (skeleton)
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py                 # Sprint 1, Dia 3
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── entities/
│       │   ├── interfaces/
│       │   └── exceptions.py
│       ├── application/
│       │   └── __init__.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── persistence/
│       │   ├── vector/
│       │   ├── embeddings/
│       │   ├── compression/
│       │   ├── extraction/
│       │   ├── splitting/
│       │   ├── security/
│       │   └── logging/
│       ├── api/
│       │   ├── __init__.py
│       │   ├── deps.py
│       │   ├── middleware/
│       │   ├── schemas/
│       │   └── routers/
│       └── web/
│           ├── __init__.py
│           ├── routes.py
│           ├── static/
│           │   └── css/
│           └── templates/
│               └── partials/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── infrastructure/
│   └── integration/
├── .env.example                            # entregue (Dia 2)
├── .gitignore                              # entregue (Dia 2)
├── .pre-commit-config.yaml                 # entregue (Dia 2)
├── alembic.ini                             # Sprint 2
├── pyproject.toml                          # entregue (Dia 2)
├── README.md                               # Sprint 8 (final)
└── LICENSE                                 # opcional, MIT
```

---

## 2. Como criar a árvore no Windows (PowerShell)

A partir da pasta onde quer hospedar o projeto:

```powershell
## Criar raiz e entrar
mkdir docuvector-lite
cd docuvector-lite

## Inicializar Git
git init -b main

## Copiar os artefatos entregues nesta sprint para os caminhos corretos
##   (copiar pyproject.toml, .env.example, .gitignore, .pre-commit-config.yaml para a raiz)
##   (copiar docker/, docs/ inteiros)

## Criar a estrutura de código (pastas vazias com .gitkeep)
$dirs = @(
    "src\docuvector\config",
    "src\docuvector\domain\entities",
    "src\docuvector\domain\interfaces",
    "src\docuvector\application",
    "src\docuvector\infrastructure\persistence",
    "src\docuvector\infrastructure\vector",
    "src\docuvector\infrastructure\embeddings",
    "src\docuvector\infrastructure\compression",
    "src\docuvector\infrastructure\extraction",
    "src\docuvector\infrastructure\splitting",
    "src\docuvector\infrastructure\security",
    "src\docuvector\infrastructure\logging",
    "src\docuvector\api\middleware",
    "src\docuvector\api\schemas",
    "src\docuvector\api\routers",
    "src\docuvector\web\static\css",
    "src\docuvector\web\templates\partials",
    "tests\unit\domain",
    "tests\unit\application",
    "tests\unit\infrastructure",
    "tests\integration",
    "migrations\versions",
    "scripts",
    "data\chroma",
    "data\hf_cache",
    ".github\workflows"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    New-Item -ItemType File -Force -Path "$dir\.gitkeep" | Out-Null
}

## Criar arquivos __init__.py vazios nas pastas Python
$initFiles = @(
    "src\docuvector\__init__.py",
    "src\docuvector\config\__init__.py",
    "src\docuvector\domain\__init__.py",
    "src\docuvector\domain\entities\__init__.py",
    "src\docuvector\domain\interfaces\__init__.py",
    "src\docuvector\application\__init__.py",
    "src\docuvector\infrastructure\__init__.py",
    "src\docuvector\infrastructure\persistence\__init__.py",
    "src\docuvector\infrastructure\vector\__init__.py",
    "src\docuvector\infrastructure\embeddings\__init__.py",
    "src\docuvector\infrastructure\compression\__init__.py",
    "src\docuvector\infrastructure\extraction\__init__.py",
    "src\docuvector\infrastructure\splitting\__init__.py",
    "src\docuvector\infrastructure\security\__init__.py",
    "src\docuvector\infrastructure\logging\__init__.py",
    "src\docuvector\api\__init__.py",
    "src\docuvector\api\middleware\__init__.py",
    "src\docuvector\api\schemas\__init__.py",
    "src\docuvector\api\routers\__init__.py",
    "src\docuvector\web\__init__.py",
    "tests\__init__.py"
)

foreach ($file in $initFiles) {
    New-Item -ItemType File -Force -Path $file | Out-Null
}

## Copiar o PDF de teste da base anterior (opcional)
##   Copy-Item ..\data_base\base\contrato_simulado_rag.pdf .\data\

## Conferir
tree /F /A | more
```

---

## 3. Bootstrap do ambiente (Sprint 1, Dia 2)

Depois de copiar todos os artefatos:

```powershell
## 1. Sincronizar ambiente com uv (instala Python 3.11 se faltar)
uv sync --extra dev

## 2. Copiar template de variáveis e EDITAR o .env
copy .env.example .env
notepad .env
##   - Gerar JWT_SECRET_KEY:
##       python -c "import secrets; print(secrets.token_hex(32))"
##   - Definir POSTGRES_PASSWORD forte
##   - Definir SEED_*_PASSWORD (mínimo 8 chars)

## 3. Subir Postgres
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps

## 4. Instalar hooks de pré-commit
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

## 5. Gerar baseline do detect-secrets (não comita .env real)
uv run detect-secrets scan --baseline .secrets.baseline

## 6. Rodar pre-commit em tudo (vai reformatar, lintar, tipar e analisar)
uv run pre-commit run --all-files

## 7. Confirmar Postgres acessível
docker exec -it docuvector-postgres psql -U docuvector_app -d docuvector -c "\dx"
##   Esperado: extensões uuid-ossp e citext listadas.
```

Se todos os passos passarem, a fundação está pronta para receber o código da Sprint 2.

---

## 4. Comandos úteis no dia a dia

| Objetivo | Comando |
|---|---|
| Subir Postgres | `docker compose -f docker/docker-compose.yml up -d` |
| Derrubar Postgres | `docker compose -f docker/docker-compose.yml down` |
| Limpar volume Postgres | `docker compose -f docker/docker-compose.yml down -v` |
| Rodar app local | `uv run uvicorn docuvector.main:app --reload` |
| Rodar testes | `uv run pytest` |
| Lint manual | `uv run ruff check src tests` |
| Format manual | `uv run ruff format src tests` |
| Tipagem manual | `uv run mypy src tests` |
| SAST manual | `uv run bandit -c pyproject.toml -r src` |
| SCA manual | `uv run pip-audit` |
| SBOM manual | `uv run cyclonedx-py environment -o sbom.json` |
| Seed de usuários | `uv run python -m scripts.seed_users` |
| Renderizar PlantUML | extensão PlantUML no VS Code (preview ao salvar) |

---

## 5. Pontos críticos de atenção

1. **Caminhos no Windows.** Sempre usar `pathlib.Path` no código, jamais hardcode de `\` ou `/`.
2. **Encoding.** Forçar `encoding="utf-8"` em qualquer `open()` de arquivo, especialmente PDFs e textos PT-BR (Windows defaulta para cp1252 e quebra acentos).
3. **`.env` real nunca vai para o Git.** O `.gitignore` cobre. `detect-secrets` é segunda linha de defesa.
4. **Volume nomeado do Postgres** (`docuvector_postgres_data`) persiste entre runs. Para reset total, usar `down -v`.
5. **ChromaDB persiste em `./data/chroma`.** Esse diretório é ignorado pelo Git, mas vive entre runs locais. Para reset, deletar a pasta.
