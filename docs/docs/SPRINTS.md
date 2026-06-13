# SPRINTS — JurisVector

**Projeto:** JurisVector (ex-DocuVector Lite)
**Repositório:** `github.com/Frausino/docuvector-lite`
**Período total:** Maio — Junho 2026

---

## Sprint 1 — Fundação e CI/CD

**Objetivo:** estrutura base do projeto com pipeline CI funcional.

**Entregáveis:**
- Clean Architecture com 4 camadas (domain, application, infrastructure, presentation)
- FastAPI com lifespan, exception handlers e rate limiting
- PostgreSQL em Docker com Alembic (migration `0001`)
- GitHub Actions CI: ruff, mypy, bandit, pytest, pip-audit
- `just` como task runner com receitas `ci`, `dev`, `migrate`, `test`
- Health check endpoint

**Decisões técnicas:**
- `uv` como gestor de pacotes (lockfile reproducível)
- `@lru_cache` para singletons (engine, session factory, stores)
- `structlog` para logging estruturado

---

## Sprint 2 — Autenticação e CRUD de Documentos

**Objetivo:** autenticação multi-tenant com RBAC e CRUD de documentos.

**Entregáveis:**
- JWT em cookie `HttpOnly` + esquema Bearer (dual auth)
- Bcrypt com política NIST SP 800-63B
- RBAC: roles `admin` e `user`
- CRUD completo de documentos com isolamento por `owner_id` (BOLA)
- Seed do admin via `SEED_ADMIN_*` em `.env`
- Migrations `0002` (CITEXT email) e `0003` (documents + chunks)
- Testes de integração: auth flow, register, admin CRUD

**Incidentes resolvidos:**
- INC-001: `flush()` sem `commit()` causava perda de dados
- INC-002: drift entre ORM e PostgreSQL resolvido com migration
- INC-003: `Depends` override ignorado em testes — corrigido no conftest

---

## Sprint 3 — Pipeline RAG

**Objetivo:** pipeline completo de ingestão e consulta com RAG.

**Entregáveis:**
- Extractors: PDF (pdfplumber), TXT, detecção automática de formato
- `RecursiveSplitter` com chunk_size e chunk_overlap configuráveis
- `SentenceTransformersEmbedder` (E5-small, local, sem custo)
- `OpenAIEmbedder` (text-embedding-ada-002, com rastreamento de custo)
- `ChromaVectorStore` com filtro BOLA em todas as operações
- `IngestionUseCase`: extract → split → embed → store, transições atômicas de status
- `RetrievalUseCase` com similarity_threshold
- `AnswerUseCase`: retrieval + geração LLM + audit
- `MockLlmClient` para testes sem rede
- `OllamaLlmClient` (qwen2.5:3b)
- Migration `0003`

---

## Sprint 4A — Compressão Observável

**Objetivo:** benchmark comparativo dos 4 algoritmos de compressão.

**Entregáveis:**
- Entidade `CompressionMetrics` no domínio
- 4 compressores: `Int8Compressor`, `BinaryCompressor`, `PcaCompressor`, `RandomProjectionCompressor`
- `CompressionBenchmarkUseCase`: calcula métricas sem persistir na coleção
- Retenção semântica via Pearson de matrizes de similaridade coseno
- Migration `0006` (campos de compressão nullable em `documents`)
- Botão § por documento na sidebar

---

## Sprint 4B — Observabilidade Econômica

**Objetivo:** dashboard de métricas operacionais e benchmark de embeddings.

**Entregáveis:**
- `EmbeddingBenchmarkUseCase`: latência, custo/1M tokens, tamanho/vetor
- `MetricsUseCase`: agregação de consultas por LLM, retenção por compressor, storage savings, estimativa Pinecone/Qdrant
- Dashboard web com KPIs, tabelas de latência e custo
- Migration `0004` e `0005` (ledger de auditoria decoupled)
- `SqlAlchemyAuditRepository` append-only

---

## Sprint 5 — Frontend JurisVector

**Objetivo:** interface web completa com SSR Jinja2+HTMX.

**Entregáveis:**
- `base.html` com navegação, JurisVector branding, gradiente indigo
- `chat.html`: sidebar de documentos, área de consulta, histórico sessionStorage
- `dashboard.html`: métricas operacionais, saúde do corpus
- `login.html`, `register.html`, `admin.html`
- JWT via cookie `HttpOnly` no frontend (SESSION_COOKIE_NAME)
- `require_authenticated_user` aceita cookie OU header Bearer
- Queries predefinidas clicáveis (sem auto-submit)
- Tema jurídico: linguagem, exemplos e copy voltados para contratos e petições

---

## Sprint 6 — Múltiplas Coleções e Métricas IR

**Objetivo:** indexar em 5 coleções Chroma e comparar qualidade do retrieval.

**Entregáveis:**

### Infraestrutura
- `CompressedVectorStore`: wrapper que comprime antes de indexar (Int8, Binary, RP)
- `CorpusPcaStore`: PCA global com `fit_corpus()` explícito, sem efeito colateral em `search`

### Use Cases
- `MultiCollectionIngestionUseCase`: ingestão + replicação nas 4 coleções comprimidas
- `CompareRetrievalUseCase`: Recall@K, Precision@K, MRR (com deduplicação de doc_ids para evitar Recall > 100%)
- `CompressToCollectionUseCase`: compressão sob demanda com persistência + texto preservado do PostgreSQL + idempotência via delete antes de add

### Frontend
- Seletor de coleção no chat com badges visuais (original/int8/binary/rp/pca)
- Comparação A/B de respostas entre duas coleções
- Botões de análise inline por mensagem (Comparar coleções, A/B, Follow-up)
- Menu dropdown por documento: "Comprimir e indexar como Int8/Binary/RP/PCA"
- Badge de confiança calibrado (Alta confiança / Confiança parcial / Contexto fraco)
- Dashboard redesenhado: cards visuais, seção de saúde do corpus, comparação IR

### Infraestrutura operacional
- Seed automático do admin no lifespan da aplicação
- Validação de existência do usuário no banco em `require_authenticated_user`
- Migration `0007` (audit actions da Sprint 6)
- Settings com collection names configuráveis via env

### Correções
- Recall@K deduplicação de document_ids (fix Recall > 100%)
- Texto preservado nas coleções comprimidas (fix RAG em Int8/Binary/RP/PCA)
- Idempotência forte com `delete_document` antes de `add_chunks`
- `contextlib.suppress(DocuvectorError)` em lugar de try/except/pass

**5 coleções Chroma:**

| Coleção | Tipo | Dims | Bytes/vetor |
|---|---|---|---|
| `docuvector` | float32 | 384 | 1536 B |
| `docuvector_int8` | int8 | 384 | 384 B |
| `docuvector_binary` | uint8 | 384 | 48 B |
| `docuvector_pca` | float32 | 192 | 768 B |
| `docuvector_rp` | float32 | 192 | 768 B |

---

## Status final

| Sprint | Status | Cobertura |
|---|---|---|
| 1 — Fundação | ✅ Fechada | — |
| 2 — Auth + CRUD | ✅ Fechada | — |
| 3 — Pipeline RAG | ✅ Fechada | — |
| 4A — Compressão | ✅ Fechada | — |
| 4B — Observabilidade | ✅ Fechada | — |
| 5 — Frontend | ✅ Fechada | — |
| 6 — Multi-coleção + IR | ✅ Fechada | 86.34% |

`just ci` → ruff ✅ · mypy ✅ · bandit ✅ · pytest 345 passed ✅ · coverage 86.34% ✅
