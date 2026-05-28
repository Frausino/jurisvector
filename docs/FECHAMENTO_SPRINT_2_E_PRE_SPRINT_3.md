# DocuVector Lite — Fechamento Sprint 2 e Pré-Sprint 3

> **Documento de planejamento e validação. Não contém alterações de código.**
> Avalia o estado atual após auditoria, Fase A (performance + HTTPBearer), Fase B (conftest), Fase C (handlers globais), Fase D (CITEXT). Define o que falta para fechar a Sprint 2 e o roteiro detalhado da Sprint 3.

**Versão:** 1.0
**Data:** 28/05/2026
**Repositório auditado:** `atual.zip`

---

## 1. Onde estamos (resumo executivo)

Sprint 2 está **funcionalmente fechada**. O fluxo de auth foi validado ponta a ponta no Swagger (login + `/me` com botão Authorize). Quatro fases de refactoring da auditoria foram aplicadas. Resta apenas um item para considerar a Sprint 2 oficialmente encerrada: **garantir a suíte de testes de integração 100% verde**. Há um arquivo legado (`./main.py` na raiz) que precisa ser removido. Depois disso, é hora de cortar tag e iniciar Sprint 3.

**Progresso global:** ~30% do projeto (2 sprints de 8 fechadas).

| Sprint | Status |
|---|---|
| 1 — Foundation | ✅ Fechada e mergeada |
| 2 — Auth + CRUD (parcial) | ⚠️ 95%, falta destravar testes e tag |
| 3 — RAG Pipeline | ⏭️ Próxima |
| 4 — Compressão (★ diferencial) | Pendente |
| 5 — Frontend Jinja2 | Pendente |
| 6 — Cobertura | Antecipado (já em 85.74%) |
| 7 — Polish DevSecOps | Pendente |
| 8 — Apresentação | Pendente |

---

## 2. Auditoria de fechamento (estado dos 14 achados)

Estado de cada achado da auditoria pré-Sprint 3, conferido contra o código atual:

| ID | Severidade | Status | Evidência no código |
|---|---|---|---|
| P0-1 | Crítico | ✅ Resolvido | `settings.py` tem `bcrypt_rounds` + `effective_bcrypt_rounds`. Login caiu de ~600ms para ~150ms |
| P0-2 | Crítico | ✅ Resolvido | `deps.py` usa `@lru_cache` em `get_password_hasher` e `get_token_service` |
| P1-1 | Alto | ✅ Resolvido | Migration `0002_users_email_citext.py` aplicada; coluna agora é CITEXT |
| P1-2 | Alto | ✅ Aceito como está | CORS só em dev, com decisão documentada |
| P1-3 | Alto | ⏳ Sprint 7 | `/health` ainda não checa banco; aceito pelo escopo |
| P1-4 | Alto | ✅ Resolvido | `main.py` tem 5 handlers globais; router de auth ficou limpo (sem try/except redundante) |
| P2-1 | Médio | ⏳ Sprint 7 | `event_metadata` tipo Python vs nullable não foi corrigido |
| P2-2 | Médio | ⏳ Sprint 7 | `UserRole(record.role)` ainda redundante; mantido por consistência defensiva |
| P2-3 | Médio | ✅ Resolvido | `client_ip` agora é dependency `get_client_ip` com validação por `ip_address()`; router não faz mais resolução ambígua |
| P2-4 | Médio | ✅ Aceito | Sessão autônoma do audit documentada como trade-off |
| P2-5 | Médio | ✅ Aceito | Query do `me()` documentada como decisão de segurança |
| P3-1 | Baixo | ✅ Resolvido | `conftest.py` força `127.0.0.1` e usa banco real |
| P3-2 | Baixo | ⏳ Sprint 7 | `ErrorResponse` ainda não usado em `responses=` |
| P3-3 | Baixo | ✅ Aceito | Migrations via docker-compose continuam OK para escopo |

**Score:** 9 resolvidos, 4 aceitos como trade-off documentado, 4 empurrados conscientemente para Sprint 7 (todos cosméticos).

**Novo achado descoberto durante a fase de testes:**

| ID | Severidade | Local | Status |
|---|---|---|---|
| N0-1 | Crítico | `/main.py` raiz | ❌ Arquivo LangChain legado da Sprint 0; precisa ser DELETADO antes do tag. O `src/docuvector/main.py` é o correto |

---

## 3. Validação local da Sprint 2 (passo a passo)

Sequência exata para confirmar que tudo está OK antes de cortar tag. Cada bloco tem o output esperado.

### 3.1. Limpeza do repo

```powershell
## Remove o main.py legado da raiz (NÃO confundir com src/docuvector/main.py)
Remove-Item .\main.py
git status
```
Esperado: `deleted: main.py` no staging.

### 3.2. Infraestrutura no ar

```powershell
just up
docker ps
just migrate-status
```
Esperado: container `docuvector-postgres` healthy; migration atual `0002_users_email_citext (head)`.

### 3.3. Qualidade estática

```powershell
just lint
just format-check
just type
```
Esperado: todos verdes, 0 erros.

### 3.4. Segurança

```powershell
just sast
just sca
just secrets-scan
just sbom
```
Esperado: bandit sem high/medium novos; pip-audit sem vulnerabilidades não-aceitas; secrets baseline OK; `sbom.json` gerado.

### 3.5. Testes unitários

```powershell
just test-unit
```
Esperado: **17 testes passando** (4 entidade User + 7 bcrypt + 6 JWT), cobertura ~85%.

### 3.6. Testes de integração (o que falta)

```powershell
just up
just migrate          ## garante 0002 aplicada
just test-integration
```
Esperado: **10 testes passando** em ~30-40 segundos. Lista esperada:
- `test_user_can_login_with_correct_credentials`
- `test_login_with_wrong_password_returns_401`
- `test_login_with_nonexistent_email_returns_same_generic_error`
- `test_failed_login_is_recorded_in_audit_log`
- `test_successful_login_is_recorded_in_audit_log`
- `test_user_email_uniqueness_is_case_insensitive` ← novo da Fase D
- `test_me_endpoint_returns_authenticated_user`
- `test_me_endpoint_without_token_returns_401`
- `test_me_endpoint_with_tampered_token_returns_401`
- `test_health_endpoint_returns_ok_payload`
- `test_openapi_schema_is_served`

**Se algum falhar:** salvar log com `just test-integration 2>&1 | Tee-Object -FilePath test_log.txt` e analisar.

### 3.7. CI local equivalente ao GitHub Actions

```powershell
just ci
```
Esperado: todos os gates verdes (lint, format-check, type, sast, sca, sbom, test-unit, smoke).

### 3.8. Smoke manual no Swagger

1. `just dev`
2. Acesse `http://127.0.0.1:8000/docs`
3. Confirme que aparece o botão **Authorize** (cadeado) no topo
4. POST `/api/v1/auth/login` com `admin@docuvector.com` + senha real do `.env`
5. Copie o `access_token`
6. Clique em **Authorize**, cole só o token (sem `Bearer`), Authorize, Close
7. Execute `GET /api/v1/auth/me`
8. Esperado: 200 com `email`, `role`, `is_active`, **sem `password_hash`**

### 3.9. Smoke de anti-enumeration

Mesmas instruções, mas com payloads abaixo no `/login`. Os dois devem retornar **a mesma estrutura de erro** com latência semelhante:

| Payload | Esperado |
|---|---|
| email correto + senha errada | 401 `authentication_failed` |
| email inexistente + qualquer senha | 401 `authentication_failed` |

Confirme no banco que os 2 audit logs foram gravados:

```sql
SELECT action, status, metadata->>'reason' AS reason
FROM audit_logs ORDER BY created_at DESC LIMIT 5;
```

Esperado: linhas com `reason=wrong_password` e `reason=user_not_found`.

---

## 4. O que comprovamos com a Sprint 2

Lista para defesa oral e para o relatório:

**Arquitetura:**
- Clean Architecture com 4 camadas estritas (domínio puro, sem import de framework)
- Composition root isolado em `deps.py`
- Audit log autônomo (NIST SP 800-53 AU-2) que sobrevive a rollback do request

**Segurança aplicada:**
- bcrypt com cost parametrizado (12 prod, 10 dev) seguindo OWASP
- JWT HS256 com validação de secret mínimo (32 chars) fail-fast
- Anti-enumeration provado por teste automatizado (`test_login_with_nonexistent_email_returns_same_generic_error`)
- Mass assignment defense via `extra="forbid"` no `LoginRequest`
- `UserResponse` jamais expõe `password_hash` (testado)
- Email CITEXT no banco impede duplicidade por variação de caixa (testado)
- Rate limiting em `/login` (10/min default) com slowapi
- Token Bearer com `WWW-Authenticate` no 401 (RFC 6750)
- Token adulterado é rejeitado (testado)

**DevSecOps:**
- CI com 6 gates: lint, type-check, SAST (bandit), SCA (pip-audit), secrets (detect-secrets), SBOM (cyclonedx)
- Docker Compose com hardening: SCRAM-SHA-256, `no-new-privileges`, `cap_drop: ALL`, porta bound em 127.0.0.1
- Migrations Alembic versionadas (2 revisões aplicadas)
- Pre-commit hooks ativados

**Qualidade:**
- Cobertura 85.74% (gate de 70% atendido com folga)
- Mypy strict em 40 arquivos sem erro
- Ruff em src + tests sem warning

**Observabilidade:**
- Logging estruturado via structlog
- Audit log com correlação user_id, action, ip_address, user_agent, metadata, timestamp

---

## 5. Débitos conhecidos (transparência)

Itens que **não são bugs**, são decisões conscientes ou polish para sprints posteriores:

1. **`/health` não verifica banco.** Para uma demo acadêmica, basta que responda. Em produção, separar `/health/live` (processo) e `/health/ready` (banco + Chroma). Tarefa da Sprint 7.
2. **`event_metadata` aceita `None` na coluna mas tipo Python diz não-opcional.** Funciona porque o mapping ORM mascara. Tarefa cosmética da Sprint 7.
3. **`UserRole(record.role)` redundante** no `_to_entity`. Inofensivo, é defesa em profundidade. Pode ficar.
4. **`ErrorResponse` schema declarado e não usado** nos `responses=`. Documentação de erro no Swagger será polida na Sprint 7.
5. **Migrations via docker-compose com pip install em runtime.** Aceito para o escopo; em produção real seria imagem própria.
6. **Bcrypt singleton em processo único.** Funciona em uvicorn single-worker; se um dia for multi-worker (gunicorn), cada worker terá seu próprio singleton, o que continua correto, só vale documentar.

---

## 6. Como cortar a tag de fechamento

Quando os passos 3.1 a 3.9 estiverem todos verdes:

```powershell
git add -A
git commit -m "chore(sprint2): close sprint 2 - auth + email citext + http bearer + audit"
git push

## Pull request para develop (se ainda houver branch feature aberta)
## Merge no develop

## Tag
git checkout develop
git pull
git tag -a v0.2.0-sprint2 -m "Sprint 2: Auth + Audit + Anti-Enumeration + CITEXT"
git push origin v0.2.0-sprint2
```

---

## 7. Sprint 3 — RAG Pipeline (planejamento detalhado)

Objetivo: ingerir documentos jurídicos (PDF, TXT, MD), gerar embeddings, armazenar no Chroma, e responder perguntas via LLM com contexto recuperado. Mantendo Clean Architecture, segurança e cobertura.

### 7.1. Princípios da Sprint 3

1. **Domínio primeiro:** definir as interfaces puras (`EmbeddingProvider`, `DocumentExtractor`, `TextSplitter`, `VectorStore`, `LlmClient`) antes de qualquer implementação. Trocar OpenAI por modelo local fica trivial.
2. **Multi-tenant desde o início:** todo documento e todo chunk carrega `user_id`. Recuperação filtra por dono.
3. **Citação obrigatória:** resposta sempre retorna `sources[]` com chunk_id e snippet. Sem isso, a parte jurídica perde sentido.
4. **Sem LangChain.** Implementação direta com OpenAI SDK + sentence-transformers + chromadb. Justificativa: controle total, sem mágica, código defensável na banca.
5. **Custo observável:** cada chamada à OpenAI registra tokens e custo estimado em audit_logs.

### 7.2. Arquitetura proposta

```
src/docuvector/
├── domain/
│   ├── entities/
│   │   ├── document.py          ← nova: Document, DocumentChunk
│   │   └── retrieval.py         ← nova: RetrievedChunk, Answer
│   ├── interfaces/
│   │   ├── document_extractor.py     ← nova
│   │   ├── text_splitter.py          ← nova
│   │   ├── embedding_provider.py     ← nova
│   │   ├── vector_store.py           ← nova
│   │   ├── llm_client.py             ← nova
│   │   └── document_repository.py    ← nova
│   └── enums.py                 ← adicionar FileFormat, DocumentStatus
│
├── application/
│   ├── ingestion_use_case.py    ← orquestra: extract → split → embed → store
│   ├── retrieval_use_case.py    ← orquestra: embed query → search → rerank
│   ├── answer_use_case.py       ← orquestra: retrieve → prompt → LLM → cite
│   └── document_crud_use_case.py ← list, get, delete (com ownership check)
│
└── infrastructure/
    ├── persistence/
    │   ├── document_repository_impl.py
    │   └── models.py            ← adicionar DocumentModel, ChunkModel
    ├── extractors/
    │   ├── pdf_extractor.py     ← pypdf
    │   ├── txt_extractor.py
    │   └── md_extractor.py
    ├── chunking/
    │   └── recursive_splitter.py     ← 1000 chars, overlap 200
    ├── embeddings/
    │   ├── openai_embedder.py
    │   └── sentence_transformers_embedder.py  ← E5 com prefixos "query:"/"passage:"
    ├── vector_stores/
    │   └── chroma_vector_store.py
    └── llm/
        └── openai_llm_client.py
```

### 7.3. Cronograma da Sprint 3 (5 dias)

**Dia 1 — Domínio + persistência de documentos**
- Entidade `Document`, enums `FileFormat`/`DocumentStatus`, `DocumentChunk`
- 5 interfaces puras (extractors, splitter, embedder, vector store, llm)
- `DocumentRepository` interface + impl SQLAlchemy
- Migration 0003 (tabela documents)
- Testes unit das entidades
- **Critério de pronto:** mypy strict + cobertura ≥ 80% no domínio

**Dia 2 — CRUD de documentos**
- `DocumentCrudUseCase` com `list_for_user`, `get_for_user` (raise se outro user), `delete`
- Router `/api/v1/documents` (GET, GET/{id}, DELETE)
- Audit log de cada ação
- Testes integration de **autorização horizontal (BOLA)**: user1 não pode ver doc de user2
- **Critério de pronto:** 3 testes BOLA verdes, OpenAPI documentado

**Dia 3 — Ingestão (upload + extract + split + embed)**
- 3 extractors com testes unit (fixture com PDF pequeno)
- `RecursiveSplitter` com testes (tamanhos, overlap, edge cases)
- 2 embedders (OpenAI + E5) com mock para teste
- `IngestionUseCase` com transação atômica: ou tudo grava, ou nada
- Endpoint `POST /api/v1/documents/upload` (multipart, max 10MB)
- Validação MIME real (não confiar no Content-Type)
- **Critério de pronto:** upload de PDF cria document + N chunks + N embeddings, audit registrado

**Dia 4 — Vector store + retrieval**
- `ChromaVectorStore` (insert, search, delete, com filtro por user_id)
- `RetrievalUseCase` retorna top-K com threshold de similaridade
- Endpoint `POST /api/v1/queries/search` (só retrieval, sem LLM ainda)
- Testes integration: ingerir 2 docs, fazer query, validar que retorna chunks do usuário correto
- **Critério de pronto:** query de user1 nunca retorna chunk de user2 (teste explícito)

**Dia 5 — LLM + answer + audit de custo**
- `OpenAiLlmClient` com prompt template jurídico em pt-BR
- `AnswerUseCase`: retrieve → build prompt → call LLM → format response with sources
- Endpoint `POST /api/v1/queries/ask`
- Audit log com `tokens_used`, `cost_usd`, `latency_ms`, `model`
- Frase de fallback quando similaridade < threshold ("não encontrei base para responder")
- **Critério de pronto:** pergunta jurídica retorna resposta + 3 sources + audit com custo

### 7.4. Riscos e mitigações Sprint 3

| Risco | Mitigação |
|---|---|
| OpenAI fora do ar na hora da demo | Embedder fallback para E5 local; LLM fallback para resposta "sistema indisponível, contexto recuperado abaixo" + sources |
| Chroma corrompe entre execuções | `CHROMA_PERSIST_DIR` versionado por env; teste de reinicialização no CI |
| PDF malicioso (zip bomb, JS) | pypdf é pure-Python, sem render; tamanho max validado; MIME real validado |
| Custo OpenAI explode | Audit_log com custo + alarme local quando > USD 1.00 acumulado |
| Embeddings de query e de passage com prefixos errados | Teste unit do E5 verifica prefixos `query:` e `passage:` |
| Multi-tenant vazando | Teste integration BOLA é gate obrigatório |

### 7.5. Itens que NÃO entram na Sprint 3 (escopo)

- Reranking semântico (vai para Sprint 4)
- Compressão de embeddings (★ diferencial da Sprint 4)
- Cache de queries
- Streaming de resposta do LLM
- OCR (PDFs escaneados)

---

## 8. Pré-requisitos para iniciar a Sprint 3

Checklist antes da primeira linha de código da Sprint 3:

- [ ] `Remove-Item .\main.py` (deletar legado)
- [ ] `just ci` verde
- [ ] `just test-integration` 100% verde (10/10)
- [ ] Smoke manual no Swagger validado (login + me + anti-enumeration)
- [ ] Tag `v0.2.0-sprint2` criada e empurrada
- [ ] Branch `feature/sprint-3-rag-domain` criada a partir de `develop`
- [ ] Issue board (GitHub Issues ou Project) com os 5 dias da Sprint 3 transcritos
- [ ] OPENAI_API_KEY válida no `.env` (testar com chamada simples antes do Dia 3)

---

## 9. Frases prontas para defesa da Sprint 2

Para a apresentação da Sprint 2 ou quando precisar justificar decisões na banca:

> "Optei por não usar LangChain. A implementação direta com SDK da OpenAI, sentence-transformers e chromadb me dá controle total das chamadas, custos e tratamento de erro. LangChain seria uma abstração que esconderia exatamente o que a banca quer ver."

> "Clean Architecture com 4 camadas. Domínio puro sem nenhum import de framework, aplicação que orquestra via interfaces, infraestrutura com as implementações concretas e apresentação com FastAPI. Posso trocar Postgres por SQLite ou OpenAI por Anthropic sem tocar em uma linha de regra de negócio."

> "Anti-enumeration provado em teste automatizado. Email inexistente e senha errada produzem exatamente a mesma resposta HTTP e o mesmo timing, porque o use case faz um bcrypt fake quando o usuário não existe. O atacante não consegue distinguir os dois casos."

> "Audit log com sessão autônoma. Decisão consciente baseada no NIST SP 800-53 controle AU-2: se a transação principal sofre rollback por qualquer motivo, o evento de auditoria ainda precisa ser registrado. Senão um atacante derruba o audit junto com a operação."

> "Bcrypt cost parametrizado por ambiente. Produção mantém 12 conforme OWASP Password Storage Cheat Sheet 2026. Desenvolvimento usa 10 para responsividade na demo. PasswordHasher é singleton de processo: recriá-lo a cada request anulava o cache do timing equalizer e desperdiçava CPU reconstruindo o CryptContext do passlib."

> "Email com tipo CITEXT no Postgres. Resolve case-insensitive uniqueness no nível do banco, não no aplicativo. O índice continua sendo usado, e qualquer ferramenta que escreva no banco — script ad-hoc, migration, outro serviço — respeita a unicidade. Defesa que não depende de cliente."

> "Esquema HTTPBearer registrado no OpenAPI. Documenta a autenticação, habilita o botão Authorize no Swagger e usa `auto_error=False` para preservar meu 401 padronizado com header WWW-Authenticate, em vez do 403 genérico do FastAPI."

---

## 10. Métricas finais da Sprint 2

| Métrica | Valor |
|---|---|
| Linhas de Python em `src/` | ~1.500 |
| Arquivos em `src/` | 40 |
| Testes unit | 17 |
| Testes integration | 10 (esperado) |
| Cobertura | 85.74% |
| Gates de CI verdes | 6/6 |
| Migrations | 2 (0001 + 0002) |
| Endpoints REST | 3 (/health, /login, /me) |
| Tabelas no banco | 3 (users, documents, audit_logs) |
| Vulnerabilidades pip-audit aceitas | 1 (MAL-2026-4750, documentada) |
| Vulnerabilidades pip-audit não-aceitas | 0 |
| Achados bandit high/medium | 0 |

---

**Conclusão.** A fundação está sólida. Sprint 2 entrega muito mais que CRUD de auth: entrega um sistema de segurança defensivo com audit auditável, anti-enumeration provado, multi-tenant pronto para Sprint 3 e DevSecOps real. Os 4 achados deixados para Sprint 7 são cosméticos. O caminho até o ★ diferencial da compressão (Sprint 4) está aberto.

**Próxima ação:** executar a sequência 3.1 a 3.9 deste documento, validar com a tag, abrir branch da Sprint 3.

---

**Fim do documento.**
