## =============================================================
## DocuVector Lite — Justfile
## Instalar: winget install Casey.Just  (Windows)
## Listar receitas: just
## Rodar receita: just <nome>
## =============================================================

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

## Força UTF-8 em subprocessos Python no Windows.
export PYTHONUTF8 := "1"
export PYTHONIOENCODING := "utf-8"
export PYTHONLEGACYWINDOWSSTDIO := "0"

default:
    @just --list

## =============================================================
## Bootstrap
## =============================================================

sync:
    uv sync --extra dev --extra api

bootstrap: sync precommit-install secrets-baseline
    @echo "Bootstrap concluído"

precommit-install:
    uv run pre-commit install
    uv run pre-commit install --hook-type pre-push

secrets-baseline:
    uv run detect-secrets scan --baseline .secrets.baseline

## =============================================================
## Qualidade de código
## =============================================================

lint:
    uv run ruff check ./src ./tests

lint-fix:
    uv run ruff check ./src ./tests --fix

format-check:
    uv run ruff format ./src ./tests --check

format:
    uv run ruff format ./src ./tests

fix:
    uv run ruff check ./src ./tests --fix
    uv run ruff format ./src ./tests

type:
    uv run mypy ./src ./tests

## =============================================================
## Segurança
## =============================================================

sast:
    uv run bandit -c pyproject.toml -r ./src

## SCA: sem --strict porque o projeto local é instalado como editable pelo uv.
## MAL-2026-4750 é ignorado temporariamente apenas enquanto FastAPI não publicar versão corrigida.
sca:
    uv run pip-audit --skip-editable --ignore-vuln MAL-2026-4750

secrets-scan:
    uv run detect-secrets scan --baseline .secrets.baseline

sbom:
    uv run cyclonedx-py environment -o sbom.json

## =============================================================
## Testes
## =============================================================

smoke:
    uv run pytest tests/integration/test_health.py --no-cov -q

test:
    uv run pytest

test-unit:
    uv run pytest tests/unit -m unit

test-integration:
    uv run pytest tests/integration -m integration

## =============================================================
## Pipeline local equivalente ao CI
## =============================================================

ci:
    uv run ruff check ./src ./tests
    uv run ruff format ./src ./tests --check
    uv run mypy ./src ./tests
    uv run bandit -c pyproject.toml -r ./src
    uv run pip-audit --skip-editable --ignore-vuln MAL-2026-4750
    uv run cyclonedx-py environment -o sbom.json
    uv run pytest tests/integration/test_health.py --no-cov -q
    @echo "CI local OK"

precommit:
    uv run pre-commit run --all-files

## =============================================================
## Docker / Postgres
## =============================================================

up:
    docker compose -f docker/docker-compose.yml up -d

down:
    docker compose -f docker/docker-compose.yml down

down-clean:
    docker compose -f docker/docker-compose.yml down -v

ps:
    docker compose -f docker/docker-compose.yml ps

logs:
    docker compose -f docker/docker-compose.yml logs -f postgres

psql:
    docker exec -it docuvector-postgres psql -U docuvector_app -d docuvector

## =============================================================
## Aplicação
## =============================================================

dev:
    uv run uvicorn docuvector.main:app --reload --host 127.0.0.1 --port 8000

serve:
    uv run uvicorn docuvector.main:app --host 0.0.0.0 --port 8000

## =============================================================
## Manutenção
## =============================================================

clean:
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .ruff_cache, .mypy_cache, .pytest_cache, htmlcov
    Remove-Item -Force -ErrorAction SilentlyContinue .coverage, coverage.xml, sbom.json
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

clean-all: clean
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .venv
    Remove-Item -Force -ErrorAction SilentlyContinue uv.lock
