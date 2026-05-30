# DocuVector Lite — Comandos diários e fluxo de sprint

## 1) Rotina diária

### Antes de começar
```bash
git status
uv sync --extra api --extra dev
uv run pre-commit install
```

### Subir o ambiente
```bash
just up
just migrate
just seed-admin
```

### Verificação rápida
```bash
just lint
just type
```

### Testes
```bash
just test-unit
just test-integration
```

### Fechar ciclo local
```bash
just test
```

---

## 2) Fluxo inteligente de trabalho

### Quando alterar código de aplicação
1. Editar arquivos.
2. Rodar:
```bash
just lint
just type
```
3. Se passar, rodar:
```bash
just test-unit
```
4. Se mexeu em banco, autenticação, permissões ou sessão:
```bash
just test-integration
```

### Quando alterar API, dependências ou sessão de banco
```bash
just migrate
just test-integration
```

### Quando alterar segurança, autenticação ou auditoria
```bash
just test-integration
just test-unit
```

### Quando alterar parsing, embeddings ou ingestão
```bash
just test-unit
just test-integration
```

---

## 3) Fluxo por tipo de mudança

### A. Mudança pequena e local
Exemplo: refatorar função, ajustar validação, corrigir lint.
```bash
just lint
just type
just test-unit
```

### B. Mudança de integração
Exemplo: login, registro, admin, persistência, sessão SQLAlchemy.
```bash
just lint
just type
just test-integration
```

### C. Mudança de schema ou migration
Exemplo: enum, tabela, coluna, índice, FK.
```bash
just migrate
just test-integration
```

### D. Mudança de segurança
Exemplo: senha, token, autorização, auditoria, rate limit.
```bash
just lint
just type
just test-unit
just test-integration
```

### E. Mudança de ingestão / RAG
Exemplo: split, embeddings, vector store, extractor.
```bash
just lint
just type
just test-unit
just test-integration
```

---

## 4) Checklist antes do commit

```bash
git status
just lint
just type
just test-unit
just test-integration
```

Se tudo estiver verde:
```bash
git add .
git commit -m "..."
git push
```

---

## 5) Comandos de diagnóstico rápido

### Ver ambiente Python
```bash
uv run python --version
uv run pre-commit --version
uv run ruff --version
uv run mypy --version
```

### Ver banco
```bash
just ps
just psql
```

### Ver migração
```bash
just migrate
```

### Ver cobertura
```bash
just test
```

---

## 6) Fluxo de sprint

### Início da sprint
```bash
git checkout main
git pull
git checkout -b feature/<nome>
uv sync --extra api --extra dev
uv run pre-commit install
just up
just migrate
just seed-admin
```

### Durante a sprint
Trabalhar em blocos curtos:
```bash
just lint
just type
just test-unit
```

Se tocar em integração:
```bash
just test-integration
```

### Fechamento da sprint
```bash
just test
git status
git add .
git commit -m "..."
git push -u origin feature/<nome>
```

---

## 7) Quando parar e investigar

Parar e investigar imediatamente se aparecer:

- `authentication_failed` logo após registro
- `ForeignKeyViolation`
- `invalid input value for enum`
- `commit` ausente
- `coverage` caindo por falha de teste
- `mypy` acusando protocolo incompleto
- `ruff` acusando B008 em FastAPI
- usuário criado e não encontrado no login

---

## 8) Regras de ouro

### Persistência
- `flush()` envia.
- `commit()` confirma.
- `close()` sem commit descarta.

### Autenticação
- Login que falha após registro costuma ser transação, não senha.

### Segurança
- Política de senha fica no validator.
- Hash fica no hasher.
- Auditoria não deve bloquear o fluxo principal.

### Migração
- Mudou enum no domínio? Revisar migration.
- Mudou schema? Rodar `just migrate`.
- Mudou login/registro? Rodar integração.

---

## 9) Comandos mais usados

```bash
just up
just down
just migrate
just seed-admin
just lint
just type
just test-unit
just test-integration
just test
```

---

## 10) Ordem recomendada no dia a dia

```text
1. just lint
2. just type
3. just test-unit
4. just test-integration (quando tocar em fluxo HTTP/banco)
5. just test
```

Se o código mexer em segurança, autenticação, schema ou integração com banco, não pule o passo 4.
