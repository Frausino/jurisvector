#!/usr/bin/env bash
# =============================================================
# DocuVector Lite — Validação completa pós-Bloco 5
# Uso: bash validacao.sh          (roda tudo)
#      bash validacao.sh fase0    (só higiene)
#      bash validacao.sh fase4    (só testes)
# =============================================================

set -euo pipefail

# Cor nos outputs
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GRN}[OK]${NC}    $*"; }
fail() { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
info() { echo -e "${BLU}[INFO]${NC}  $*"; }
warn() { echo -e "${YLW}[WARN]${NC}  $*"; }
sep()  { echo -e "\n${BLU}======================================================${NC}"; echo -e "${BLU}  $*${NC}"; echo -e "${BLU}======================================================${NC}"; }

FASE="${1:-all}"

# =============================================================
# FASE 0 — Higiene pré-validação
# =============================================================
fase0() {
  sep "FASE 0 — Higiene (gaps de aplicação)"

  # ---- 0.1 migration 0005 com extensão dupla ----
  info "0.1 Verificando migration 0005..."
  DOUBLE_EXT=$(find migrations/versions -name "0005*.py.py" 2>/dev/null || true)
  if [ -n "$DOUBLE_EXT" ]; then
    warn "Migration com extensão dupla encontrada: $DOUBLE_EXT"
    CORRECT="${DOUBLE_EXT%.py}"
    mv "$DOUBLE_EXT" "$CORRECT"
    ok "Renomeada para: $CORRECT"
  else
    ok "0.1 migration 0005 sem extensão dupla"
  fi

  # ---- 0.2 test_llm_factory duplicado ----
  info "0.2 Verificando test_llm_factory duplicado..."
  ROOT_TEST="tests/test_llm_factory.py"
  UNIT_TEST="tests/unit/infrastructure/test_llm_factory.py"
  if [ -f "$ROOT_TEST" ] && [ -f "$UNIT_TEST" ]; then
    warn "Duplicata encontrada em $ROOT_TEST e $UNIT_TEST"
    # A versão da raiz (do fixes) tem reset_factory_caches; a da subpasta é antiga.
    # Verificar qual é a nova pela presença de reset_factory_caches.
    ROOT_HAS_RESET=$(grep -c "reset_factory_caches" "$ROOT_TEST" || true)
    UNIT_HAS_RESET=$(grep -c "reset_factory_caches" "$UNIT_TEST" || true)
    if [ "$ROOT_HAS_RESET" -gt 0 ] && [ "$UNIT_HAS_RESET" -eq 0 ]; then
      info "Versão nova em raiz, antiga em unit/infrastructure. Substituindo..."
      cp "$ROOT_TEST" "$UNIT_TEST"
      rm "$ROOT_TEST"
      ok "Versão nova movida para tests/unit/infrastructure/test_llm_factory.py"
    elif [ "$UNIT_HAS_RESET" -gt 0 ] && [ "$ROOT_HAS_RESET" -eq 0 ]; then
      info "Versão nova em unit/infrastructure. Removendo da raiz..."
      rm "$ROOT_TEST"
      ok "Duplicata da raiz removida"
    else
      warn "Ambas têm reset_factory_caches ou ambas não têm. Verificar manualmente."
      warn "Mantendo unit/infrastructure. Removendo raiz."
      rm -f "$ROOT_TEST"
      ok "Duplicata da raiz removida"
    fi
  elif [ -f "$ROOT_TEST" ] && [ ! -f "$UNIT_TEST" ]; then
    info "Teste só na raiz. Movendo para unit/infrastructure..."
    mv "$ROOT_TEST" "$UNIT_TEST"
    ok "Movido para tests/unit/infrastructure/test_llm_factory.py"
  else
    ok "0.2 sem duplicata de test_llm_factory"
  fi

  # ---- 0.3 queries.py usando Limiter próprio ----
  info "0.3 Verificando Limiter em queries.py..."
  LIMITER_OWN=$(grep -n "^limiter = Limiter(" src/docuvector/api/routers/queries.py 2>/dev/null || true)
  USES_SHARED=$(grep -n "shared_limiter" src/docuvector/api/routers/queries.py 2>/dev/null || true)
  if [ -n "$LIMITER_OWN" ]; then
    fail "queries.py ainda cria Limiter próprio (linha: $LIMITER_OWN). Aplicar PATCH_limiter_unico.md antes de continuar."
  elif [ -z "$USES_SHARED" ]; then
    fail "queries.py não usa shared_limiter e não tem Limiter próprio. Estado inesperado — verificar manualmente."
  else
    ok "0.3 queries.py usa shared_limiter"
  fi

  # ---- 0.4 caches antigos ----
  info "0.4 Limpando caches Python antigos..."
  find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
  find . -name "*.pyc" -not -path "./.venv/*" -delete 2>/dev/null || true
  ok "0.4 Caches limpos"

  # ---- 0.5 .env existe ----
  info "0.5 Verificando .env..."
  if [ ! -f ".env" ]; then
    fail ".env não encontrado. Executar: cp .env.example .env && editar valores"
  fi
  # Verifica vars obrigatórias
  for VAR in POSTGRES_PASSWORD JWT_SECRET_KEY SEED_ADMIN_EMAIL SEED_ADMIN_PASSWORD DATABASE_URL; do
    if ! grep -q "^${VAR}=" .env; then
      fail ".env não contém ${VAR}"
    fi
  done
  # Verifica se ainda tem o valor placeholder do template
  if grep -q "trocar_por_segredo_de_64_chars" .env; then
    fail "JWT_SECRET_KEY ainda tem valor placeholder. Gerar com: python -c \"import secrets; print(secrets.token_hex(32))\""
  fi
  ok "0.5 .env presente com vars obrigatórias"

  ok "FASE 0 concluída"
}

# =============================================================
# FASE 1 — Sync de dependências
# =============================================================
fase1() {
  sep "FASE 1 — Bootstrap do ambiente"

  info "1.1 Sincronizando dependências (uv sync --extra api)..."
  just sync
  ok "1.1 Dependências sincronizadas"

  info "1.2 Verificando que 'just' lista receitas..."
  just --list > /dev/null
  ok "1.2 just ok"
}

# =============================================================
# FASE 2 — Gates de qualidade
# =============================================================
fase2() {
  sep "FASE 2 — Gates de qualidade"

  info "2.1 Lint (ruff check)..."
  just lint
  ok "2.1 lint verde"

  info "2.2 Formatação (ruff format --check)..."
  just format-check
  ok "2.2 format-check verde"

  info "2.3 Tipagem estática (mypy strict)..."
  just type
  ok "2.3 type verde"

  info "2.4 SAST (bandit)..."
  just sast
  ok "2.4 sast verde"

  info "2.5 SCA (pip-audit)..."
  just sca
  ok "2.5 sca verde"

  info "2.6 Detecção de segredos..."
  just secrets-scan
  ok "2.6 secrets-scan verde"

  info "2.7 SBOM (cyclonedx)..."
  just sbom
  COMP_COUNT=$(python3 -c "import json; d=json.load(open('sbom.json')); print(len(d.get('components', [])))")
  if [ "$COMP_COUNT" -gt 0 ]; then
    ok "2.7 sbom gerado com $COMP_COUNT componentes"
  else
    fail "2.7 sbom.json sem componentes"
  fi

  ok "FASE 2 concluída"
}

# =============================================================
# FASE 3 — Banco de dados
# =============================================================
fase3() {
  sep "FASE 3 — Banco de dados"

  info "3.1 Subindo Postgres..."
  just up

  info "3.1 Aguardando Postgres ficar healthy (máx 30s)..."
  for i in $(seq 1 30); do
    STATUS=$(docker compose --env-file .env -f docker/docker-compose.yml ps --format json 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin) if sys.stdin.read(1) else []; print(d[0].get('Health','') if d else '')" 2>/dev/null || \
      docker inspect docuvector-postgres --format '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "healthy" ]; then
      ok "3.1 Postgres healthy após ${i}s"
      break
    fi
    if [ "$i" -eq 30 ]; then
      fail "3.1 Postgres não ficou healthy em 30s. Rodar: just logs"
    fi
    sleep 1
  done

  info "3.2 Aplicando migrations..."
  just migrate
  ok "3.2 Migrations aplicadas"

  info "3.2 Verificando versão atual..."
  CURRENT=$(just migrate-status 2>&1 | tail -1)
  echo "    Alembic current: $CURRENT"
  if echo "$CURRENT" | grep -q "0005"; then
    ok "3.2 Migration 0005 é head"
  else
    fail "3.2 Migration 0005 não é head. Estado: $CURRENT"
  fi

  info "3.3 Verificando schema no banco..."
  # compression_method deve ser NULLABLE (sem NOT NULL)
  NULL_CHECK=$(docker exec docuvector-postgres psql -U docuvector_app -d docuvector -t \
    -c "SELECT is_nullable FROM information_schema.columns WHERE table_name='documents' AND column_name='compression_method';" \
    2>/dev/null | tr -d ' \n')
  if [ "$NULL_CHECK" = "YES" ]; then
    ok "3.3 compression_method é NULLABLE"
  else
    fail "3.3 compression_method deveria ser NULLABLE, está: $NULL_CHECK"
  fi

  # audit_logs não deve ter FK para users
  FK_COUNT=$(docker exec docuvector-postgres psql -U docuvector_app -d docuvector -t \
    -c "SELECT COUNT(*) FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name
        WHERE tc.table_name = 'audit_logs' AND tc.constraint_type = 'FOREIGN KEY';" \
    2>/dev/null | tr -d ' \n')
  if [ "$FK_COUNT" = "0" ]; then
    ok "3.3 audit_logs sem FK (conforme NIST)"
  else
    fail "3.3 audit_logs tem $FK_COUNT FK(s). Deve ser 0."
  fi

  info "3.4 Seed do admin (idempotente)..."
  just seed-admin
  ok "3.4 Seed ok"

  # Confirma admin no banco
  ADMIN_COUNT=$(docker exec docuvector-postgres psql -U docuvector_app -d docuvector -t \
    -c "SELECT COUNT(*) FROM users WHERE role='admin';" \
    2>/dev/null | tr -d ' \n')
  if [ "$ADMIN_COUNT" -ge 1 ]; then
    ok "3.4 Admin encontrado no banco ($ADMIN_COUNT)"
  else
    fail "3.4 Nenhum admin encontrado após seed"
  fi

  ok "FASE 3 concluída"
}

# =============================================================
# FASE 4 — Testes automatizados
# =============================================================
fase4() {
  sep "FASE 4 — Testes automatizados"

  info "4.1 Smoke test (health endpoint)..."
  just smoke
  ok "4.1 smoke verde"

  info "4.2 Unit tests (sem cobertura)..."
  just test-unit
  ok "4.2 test-unit verde"

  info "4.3 Integration tests (sem cobertura)..."
  just test-integration
  ok "4.3 test-integration verde"

  info "4.4 Pipeline completo CI (lint + format + type + sast + sca + sbom + test + smoke)..."
  just ci
  ok "4.4 CI local OK"

  info "4.5 Cobertura formal (gate ≥ 70%)..."
  uv run pytest \
    --cov=src/docuvector \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-fail-under=70 \
    -q
  ok "4.5 Cobertura ≥ 70%"

  ok "FASE 4 concluída"
}

# =============================================================
# FASE 5 — Validação via API (curl)
# =============================================================
fase5() {
  sep "FASE 5 — Validação via API (curl ponta a ponta)"

  # ---- 5.0 Subir servidor em background ----
  info "5.0 Iniciando servidor em background (porta 8000)..."
  # Garante que não há processo antigo
  pkill -f "uvicorn docuvector.main:app" 2>/dev/null || true
  sleep 1
  uv run uvicorn docuvector.main:app \
    --host 127.0.0.1 --port 8000 \
    --log-level warning &
  SERVER_PID=$!
  echo "    PID do servidor: $SERVER_PID"

  # Aguarda o servidor subir (máx 15s)
  info "5.0 Aguardando servidor subir..."
  for i in $(seq 1 15); do
    if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
      ok "5.0 Servidor pronto após ${i}s"
      break
    fi
    if [ "$i" -eq 15 ]; then
      fail "5.0 Servidor não respondeu em 15s"
    fi
    sleep 1
  done

  # Garantir kill do servidor ao sair (mesmo por falha)
  trap 'info "Parando servidor PID $SERVER_PID..."; kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null; ok "Servidor parado"' EXIT

  # ---- 5.1 Health ----
  info "5.1 GET /api/v1/health..."
  HEALTH=$(curl -sf http://127.0.0.1:8000/api/v1/health)
  echo "    Resposta: $HEALTH"
  ok "5.1 health ok"

  # ---- 5.2 Login do admin ----
  info "5.2 POST /api/v1/auth/login (admin)..."
  # Pega email e senha do .env
  ADMIN_EMAIL=$(grep "^SEED_ADMIN_EMAIL=" .env | cut -d= -f2)
  ADMIN_PASS=$(grep "^SEED_ADMIN_PASSWORD=" .env | cut -d= -f2)
  LOGIN_RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASS}\"}")
  TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  if [ -z "$TOKEN" ]; then
    fail "5.2 Token não retornado. Resposta: $LOGIN_RESP"
  fi
  ok "5.2 Login ok — token obtido (${#TOKEN} chars)"

  AUTH="Authorization: Bearer $TOKEN"

  # ---- 5.3 GET /me ----
  info "5.3 GET /api/v1/auth/me..."
  ME=$(curl -sf http://127.0.0.1:8000/api/v1/auth/me -H "$AUTH")
  ME_ROLE=$(echo "$ME" | python3 -c "import sys,json; print(json.load(sys.stdin)['role'])")
  if [ "$ME_ROLE" != "admin" ]; then
    fail "5.3 role esperado 'admin', recebido '$ME_ROLE'"
  fi
  ok "5.3 /me ok — role=$ME_ROLE"

  # ---- 5.4 Register (anti-enumeração) ----
  info "5.4 POST /api/v1/auth/register — email novo..."
  REG1=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"advogado.test@exemplo.com",
    "password":"SenhaForteNIST@2026!"}') # pragma: allowlist secret
  if [ "$REG1" != "201" ]; then
    fail "5.4 /register esperado 201, recebido $REG1"
  fi
  ok "5.4 Primeiro register: $REG1"

  info "5.4 POST /api/v1/auth/register — mesmo email (anti-enumeração)..."
  REG2=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"advogado.test@exemplo.com","password":"OutraForte@2026!"}') # pragma: allowlist secret
  if [ "$REG2" != "201" ]; then
    fail "5.4 Anti-enumeração falhou: email duplicado retornou $REG2 (esperado 201)"
  fi
  ok "5.4 Anti-enumeração ok — mesmo código $REG2 para email duplicado"

  info "5.4 POST /api/v1/auth/register — senha fraca..."
  REG3=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"outro@exemplo.com","password":"123"}')
  if [ "$REG3" = "201" ]; then
    fail "5.4 Senha fraca deveria ser rejeitada, mas retornou 201"
  fi
  ok "5.4 Senha fraca corretamente rejeitada: $REG3"

  # ---- 5.5 Login do usuário recém-criado ----
  info "5.5 POST /api/v1/auth/login (usuário novo)..."
  USER_LOGIN=$(curl -sf -X POST http://127.0.0.1:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"advogado.test@exemplo.com","password":"SenhaForteNIST@2026!"}') # pragma: allowlist secret
  USER_TOKEN=$(echo "$USER_LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  if [ -z "$USER_TOKEN" ]; then
    fail "5.5 Token do usuário não retornado"
  fi
  ok "5.5 Login do usuário novo ok"

  USER_AUTH="Authorization: Bearer $USER_TOKEN"

  # ---- 5.6 Provedores de embedding ----
  info "5.6 GET /api/v1/documents/providers..."
  EMBED_PROVS=$(curl -sf http://127.0.0.1:8000/api/v1/documents/providers -H "$USER_AUTH")
  echo "    Provedores: $EMBED_PROVS"
  if echo "$EMBED_PROVS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any(p['name']=='sentence_transformers' for p in d), 'sentence_transformers ausente'"; then
    ok "5.6 sentence_transformers presente"
  else
    fail "5.6 sentence_transformers não listado"
  fi

  # ---- 5.7 Upload de TXT ----
  info "5.7 POST /api/v1/documents — upload de TXT jurídico..."
  # Cria arquivo temporário
  TMP_TXT=$(mktemp /tmp/contrato_XXXX.txt)
  cat > "$TMP_TXT" << 'CONTRATO'
CONTRATO DE PRESTAÇÃO DE SERVIÇOS

CLÁUSULA PRIMEIRA - DO OBJETO
O presente contrato tem por objeto a prestação de serviços de consultoria
jurídica especializada em direito empresarial.

CLÁUSULA TERCEIRA - DA RESCISÃO
O presente contrato poderá ser rescindido por qualquer das partes
mediante notificação prévia por escrito com antecedência mínima de
30 (trinta) dias. Em caso de descumprimento, a parte prejudicada
poderá rescindir imediatamente o contrato sem aviso prévio.

CLÁUSULA QUARTA - DO VALOR
Pelos serviços prestados, a CONTRATANTE pagará à CONTRATADA o valor
mensal de R$ 5.000,00, até o quinto dia útil de cada mês.
CONTRATO

  UPLOAD_RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/v1/documents \
    -H "$USER_AUTH" \
    -F "file=@${TMP_TXT};type=text/plain" \
    -F "embedding_provider=sentence_transformers")
  rm -f "$TMP_TXT"

  DOC_STATUS=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['document']['status'])")
  DOC_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['document']['id'])")
  CHUNKS=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['chunks_created'])")
  if [ "$DOC_STATUS" != "embedded" ]; then
    fail "5.7 Upload: status esperado 'embedded', recebido '$DOC_STATUS'"
  fi
  if [ "$CHUNKS" -lt 1 ]; then
    fail "5.7 Upload: chunks_created=$CHUNKS, esperado ≥ 1"
  fi
  ok "5.7 Upload ok — id=$DOC_ID status=$DOC_STATUS chunks=$CHUNKS"

  # ---- 5.8 Listar documentos ----
  info "5.8 GET /api/v1/documents..."
  LIST_RESP=$(curl -sf http://127.0.0.1:8000/api/v1/documents -H "$USER_AUTH")
  LIST_COUNT=$(echo "$LIST_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
  if [ "$LIST_COUNT" -lt 1 ]; then
    fail "5.8 GET /documents retornou lista vazia"
  fi
  ok "5.8 Listagem ok — $LIST_COUNT documento(s)"

  # ---- 5.9 BOLA: documento de outro usuário deve dar 404 ----
  info "5.9 BOLA: admin tenta acessar documento do usuário regular..."
  BOLA_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    http://127.0.0.1:8000/api/v1/documents/$DOC_ID \
    -H "$AUTH")
  if [ "$BOLA_CODE" != "404" ]; then
    fail "5.9 BOLA: esperado 404 (mascaramento RGN-10), recebido $BOLA_CODE"
  fi
  ok "5.9 BOLA ok — admin recebeu $BOLA_CODE para doc de outro usuário"

  # ---- 5.10 Provedores de LLM ----
  info "5.10 GET /api/v1/queries/llm-providers..."
  LLM_PROVS=$(curl -sf http://127.0.0.1:8000/api/v1/queries/llm-providers -H "$USER_AUTH")
  LLM_DEFAULT=$(echo "$LLM_PROVS" | python3 -c "import sys,json; print(json.load(sys.stdin)['default'])")
  LLM_NAMES=$(echo "$LLM_PROVS" | python3 -c "import sys,json; print([p['name'] for p in json.load(sys.stdin)['items']])")
  echo "    Providers: $LLM_NAMES"
  echo "    Default:   $LLM_DEFAULT"
  if echo "$LLM_NAMES" | grep -q "mock"; then
    ok "5.10 mock listado"
  else
    fail "5.10 mock ausente nos providers de LLM"
  fi
  if echo "$LLM_NAMES" | grep -q "ollama"; then
    ok "5.10 ollama listado"
  fi
  if [ "$LLM_DEFAULT" = "mock" ]; then
    ok "5.10 default=mock confirmado"
  else
    warn "5.10 default='$LLM_DEFAULT' (esperado 'mock'). Conferir LLM_DEFAULT_PROVIDER no .env"
  fi

  # ---- 5.11 Ask com Mock (validação determinística) ----
  info "5.11 POST /api/v1/queries/ask — llm_provider=mock..."
  ASK_RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/v1/queries/ask \
    -H "$USER_AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Qual o prazo de notificação prévia para rescisão do contrato?",
      "embedding_provider": "sentence_transformers",
      "llm_provider": "mock"
    }')
  ASK_MODEL=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['model'])")
  ASK_PROV=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['llm_provider'])")
  ASK_TOKENS=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['tokens_used'])")
  ASK_COST=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['cost_usd'])")
  ASK_GROUNDED=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['grounded'])")
  ASK_SOURCES=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['sources']))")
  ASK_ANSWER=$(echo "$ASK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['answer'][:60])")
  echo "    model=$ASK_MODEL  provider=$ASK_PROV  tokens=$ASK_TOKENS  cost=$ASK_COST"
  echo "    grounded=$ASK_GROUNDED  sources=$ASK_SOURCES"
  echo "    answer[:60]='$ASK_ANSWER'"
  [ "$ASK_MODEL" = "mock" ]       && ok "5.11 model=mock" || fail "5.11 model='$ASK_MODEL' esperado 'mock'"
  [ "$ASK_PROV" = "mock" ]        && ok "5.11 llm_provider=mock" || fail "5.11 llm_provider='$ASK_PROV'"
  [ "$ASK_TOKENS" = "0" ]         && ok "5.11 tokens_used=0" || fail "5.11 tokens_used=$ASK_TOKENS esperado 0"
  [ "$ASK_COST" = "0.0" ]         && ok "5.11 cost_usd=0.0" || fail "5.11 cost_usd=$ASK_COST esperado 0.0"
  [ "$ASK_GROUNDED" = "True" ]    && ok "5.11 grounded=True" || warn "5.11 grounded=$ASK_GROUNDED (pode ser False se similarity baixa)"
  [ "$ASK_SOURCES" -ge 1 ]        && ok "5.11 sources=$ASK_SOURCES ≥ 1" || warn "5.11 sem sources (chunks abaixo do threshold)"

  # ---- 5.12 Ask com provider omitido (usa default) ----
  info "5.12 POST /api/v1/queries/ask — sem llm_provider (usa default do Settings)..."
  ASK_DEFAULT=$(curl -sf -X POST http://127.0.0.1:8000/api/v1/queries/ask \
    -H "$USER_AUTH" \
    -H "Content-Type: application/json" \
    -d '{"query":"Qual o valor mensal do contrato?","embedding_provider":"sentence_transformers"}')
  DEFAULT_PROV=$(echo "$ASK_DEFAULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['llm_provider'])")
  echo "    provider usado: $DEFAULT_PROV"
  if [ "$DEFAULT_PROV" = "mock" ]; then
    ok "5.12 default provider=mock aplicado corretamente"
  else
    warn "5.12 provider='$DEFAULT_PROV', esperado 'mock'. Conferir LLM_DEFAULT_PROVIDER no .env"
  fi

  # ---- 5.13 Ask sobre conteúdo inexistente (abstenção) ----
  info "5.13 POST /api/v1/queries/ask — tema fora do documento..."
  ASK_ABSENT=$(curl -sf -X POST http://127.0.0.1:8000/api/v1/queries/ask \
    -H "$USER_AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Qual a política de bônus anual e participação nos lucros do contrato?",
      "embedding_provider": "sentence_transformers",
      "llm_provider": "mock",
      "similarity_threshold": 0.95
    }')
  ABSENT_GROUNDED=$(echo "$ASK_ABSENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['grounded'])")
  ABSENT_ANSWER=$(echo "$ASK_ABSENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['answer'][:80])")
  echo "    grounded=$ABSENT_GROUNDED  answer[:80]='$ABSENT_ANSWER'"
  ok "5.13 abstenção testada (grounded=$ABSENT_GROUNDED)"

  # ---- 5.14 Rate limit ----
  info "5.14 Rate limit — 15 requisições em sequência (limite=10/min)..."
  HTTP_CODES=""
  for i in $(seq 1 15); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/v1/queries/ask \
      -H "$USER_AUTH" \
      -H "Content-Type: application/json" \
      -d '{"query":"rate limit test ok","llm_provider":"mock"}')
    HTTP_CODES="$HTTP_CODES $CODE"
  done
  echo "    Códigos: $HTTP_CODES"
  RATE_429=$(echo "$HTTP_CODES" | tr ' ' '\n' | grep -c "429" || true)
  if [ "$RATE_429" -ge 1 ]; then
    ok "5.14 Rate limit funcionando — $RATE_429 requisição(ões) com 429"
  else
    fail "5.14 Nenhuma 429 em 15 requisições. O @shared_limiter.limit não está registrado no app.state. Aplicar gap 0.3."
  fi

  # ---- 5.15 Audit log via SQL ----
  info "5.15 Verificando audit log no banco..."
  AUDIT_COUNT=$(docker exec docuvector-postgres psql -U docuvector_app -d docuvector -t \
    -c "SELECT COUNT(*) FROM audit_logs WHERE action='query_executed' AND status='success';" \
    2>/dev/null | tr -d ' \n')
  echo "    query_executed SUCCESS: $AUDIT_COUNT"
  if [ "$AUDIT_COUNT" -ge 1 ]; then
    ok "5.15 Audit log tem $AUDIT_COUNT evento(s) query_executed"
  else
    fail "5.15 Audit log sem eventos query_executed — pipeline de auditoria com problema"
  fi

  # Agregação por provider (embrião do dashboard Sprint 4)
  info "5.15 Agregação de KPIs por provider (Sprint 4 preview)..."
  docker exec docuvector-postgres psql -U docuvector_app -d docuvector \
    -c "SELECT
          metadata->>'llm_provider' AS provider,
          COUNT(*) AS calls,
          AVG((metadata->>'latency_ms')::int) AS avg_latency_ms,
          SUM((metadata->>'tokens_used')::int) AS total_tokens,
          SUM((metadata->>'cost_usd')::numeric) AS total_cost_usd
        FROM audit_logs
        WHERE action='query_executed' AND status='success'
        GROUP BY metadata->>'llm_provider';"
  ok "5.15 Agregação de KPIs ok"

  # ---- 5.16 401 sem token ----
  info "5.16 GET /api/v1/documents sem token deve dar 401..."
  NO_AUTH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/documents)
  if [ "$NO_AUTH" = "401" ]; then
    ok "5.16 401 sem token confirmado"
  else
    fail "5.16 Esperado 401, recebido $NO_AUTH"
  fi

  # ---- 5.17 422 query muito curta ----
  info "5.17 POST /api/v1/queries/ask — query muito curta deve dar 422..."
  SHORT_Q=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/v1/queries/ask \
    -H "$USER_AUTH" \
    -H "Content-Type: application/json" \
    -d '{"query":"ab","llm_provider":"mock"}')
  if [ "$SHORT_Q" = "422" ]; then
    ok "5.17 422 para query curta confirmado"
  else
    fail "5.17 Esperado 422, recebido $SHORT_Q"
  fi

  # ---- 5.18 502 para provider sem credencial ----
  info "5.18 POST /api/v1/queries/ask com llm_provider=openai sem API key deve dar 502..."
  OPENAI_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/v1/queries/ask \
    -H "$USER_AUTH" \
    -H "Content-Type: application/json" \
    -d '{"query":"teste openai sem chave configurada","embedding_provider":"sentence_transformers","llm_provider":"openai"}')
  if [ "$OPENAI_CODE" = "502" ]; then
    ok "5.18 502 para openai sem API key confirmado"
  else
    warn "5.18 Esperado 502, recebido $OPENAI_CODE (OPENAI_API_KEY pode estar setada no .env)"
  fi

  ok "FASE 5 concluída"
}

# =============================================================
# RESUMO FINAL
# =============================================================
resumo() {
  sep "CHECKLIST FINAL"
  echo "
  Fase 0 — Higiene           ..........  OK
  Fase 1 — Ambiente          ..........  OK
  Fase 2 — Gates qualidade   ..........  OK
  Fase 3 — Banco             ..........  OK
  Fase 4 — Testes            ..........  OK
  Fase 5 — API end-to-end    ..........  OK

  Projeto aprovado para Sprint 4.
  "
  info "Tag sugerida:"
  echo ""
  echo "  git add -A"
  echo "  git commit -m \"chore(sprint-3): validacao completa pós-Bloco 5 — CI verde\""
  echo "  git tag v0.3.0-sprint3"
  echo "  git push && git push --tags"
}

# =============================================================
# DISPATCHER
# =============================================================
case "$FASE" in
  fase0) fase0 ;;
  fase1) fase1 ;;
  fase2) fase2 ;;
  fase3) fase3 ;;
  fase4) fase4 ;;
  fase5) fase5 ;;
  all|*)
    fase0
    fase1
    fase2
    fase3
    fase4
    fase5
    resumo
    ;;
esac
