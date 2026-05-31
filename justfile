## =============================================================
## DocuVector Lite — Justfile
## Instalar: winget install Casey.Just  (Windows)
## Listar receitas: just
## Rodar receita: just <nome>
## =============================================================

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

## Força UTF-8 em todo subprocess Python (resolve UnicodeDecodeError em paths
## com acento no Windows; bug recorrente em pip-audit / pip-api).
export PYTHONUTF8 := "1"
export PYTHONIOENCODING := "utf-8"

## --- Default: lista as receitas disponíveis ---
default:
    @just --list

## =============================================================
## Bootstrap
## =============================================================

## Sincroniza ambiente virtual a partir do pyproject + uv.lock (dev default group + api extra)
sync:
    uv sync --extra api

## Sincroniza e instala hooks de pré-commit
bootstrap: sync precommit-install
    @echo "Bootstrap concluído"

## Instala hooks pre-commit e pre-push
precommit-install:
    uv run pre-commit install
    uv run pre-commit install --hook-type pre-push

## Gera baseline inicial de detect-secrets (rodar uma vez)
secrets-baseline:
    uv run detect-secrets scan --baseline .secrets.baseline

## Alias explícito para gerar baseline inicial de segredos
secrets-baseline-init: secrets-baseline

## =============================================================
## Qualidade de código
## =============================================================

## Lint (ruff check)
lint:
    uv run ruff check src tests

## Lint com auto-fix
lint-fix:
    uv run ruff check --fix src tests

## Corrige lint, organiza imports e aplica formatação
fix:
    uv run ruff check --fix src tests
    uv run ruff format src tests
## Corrige e valida tudo antes do commit
fix-all:
    uv run ruff check --fix src tests
    uv run ruff format src tests
    uv run mypy src tests

## Verifica formatação (não modifica)
format-check:
    uv run ruff format --check src tests

## Aplica formatação
format:
    uv run ruff format src tests

## Tipagem estática estrita
type:
    uv run mypy src tests

## =============================================================
## Segurança
## =============================================================

## SAST (Bandit)
sast:
    uv run bandit -c pyproject.toml -r src

## SCA (pip-audit) — audita o ambiente Python instalado.
## --skip-editable: ignora o próprio docuvector-lite (não está no PyPI).
## --ignore-vuln: ver justificativa em .pip-audit.toml.
sca:
    uv run pip-audit --skip-editable --ignore-vuln MAL-2026-4750

## Detecção de segredos
secrets-scan:
    uv run detect-secrets scan --baseline .secrets.baseline

## SBOM em CycloneDX JSON
sbom:
    uv run cyclonedx-py environment -o sbom.json

## =============================================================
## Testes
## =============================================================

## Smoke test rápido (sem cobertura, usado no Dia 3)
smoke:
    uv run pytest tests/integration/test_health.py --no-cov -q

## Todos os testes com cobertura (gate de 70%)
test:
    uv run pytest

## Testes unitários apenas
test-unit:
    uv run pytest tests/unit -m unit --no-cov

## Testes de integração apenas
test-integration:
    uv run pytest tests/integration -m integration --no-cov

## =============================================================
## Pipeline local equivalente ao CI
## =============================================================

## Roda tudo que o GitHub Actions vai rodar (em ordem)
ci: lint format-check type sast sca sbom test smoke
    @echo "CI local OK"

## Rodar todos os hooks de pre-commit em todos os arquivos
precommit:
    uv run pre-commit run --all-files

## =============================================================
## Docker / Postgres
## =============================================================

## Sobe Postgres em background
up:
    docker compose --env-file .env -f docker/docker-compose.yml up -d

## Derruba containers (mantém volume)
down:
    docker compose --env-file .env -f docker/docker-compose.yml down

## Derruba containers e apaga volume (reset total do banco)
down-clean:
    docker compose --env-file .env -f docker/docker-compose.yml down -v

## Status dos containers
ps:
    docker compose --env-file .env -f docker/docker-compose.yml ps

## Logs ao vivo do Postgres
logs:
    docker compose --env-file .env -f docker/docker-compose.yml logs -f postgres

## Shell psql dentro do container (pede senha do POSTGRES_PASSWORD)
psql:
    docker exec -it docuvector-postgres psql -U docuvector_app -d docuvector

## =============================================================
## Aplicação
## =============================================================

## Roda servidor de desenvolvimento com auto-reload
dev:
    uv run uvicorn docuvector.main:app --reload --host 127.0.0.1 --port 8000

## Roda servidor sem reload (mais próximo de produção)
serve:
    uv run uvicorn docuvector.main:app --host 0.0.0.0 --port 8000

## =============================================================
## Bootstrap operacional
## =============================================================

## Cria APENAS o admin de bootstrap a partir do .env (idempotente).
## Demais usuários nascem via POST /api/v1/auth/register (público) ou
## via POST /api/v1/admin/users (admin-only).
seed-admin:
    uv run python -m scripts.seed_admin

## =============================================================
## Migrations Alembic
## =============================================================

## Aplica migrations Alembic
migrate:
    uv run alembic upgrade head

## Cria nova migration por auto-generate
migration name:
    uv run alembic revision --autogenerate -m "{{name}}"

## Reverte uma migration
migrate-down:
    uv run alembic downgrade -1

## Mostra migrations aplicadas
migrate-status:
    uv run alembic current

## =============================================================
## Manutenção
## =============================================================

## Limpa caches locais
clean:
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .ruff_cache, .mypy_cache, .pytest_cache, htmlcov, .coverage, coverage.xml, sbom.json

## Limpa caches + venv (cuidado)
clean-all: clean
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .venv
