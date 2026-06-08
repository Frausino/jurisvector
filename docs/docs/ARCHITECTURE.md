# ARCHITECTURE — JurisVector

**Versão:** 1.0
**Data:** Junho 2026
**Autor:** Davi Rosa F. e Breno Manoel
**Repositório:** `github.com/Frausino/docuvector-lite`

---

## 1. Visão geral

JurisVector é um sistema RAG (Retrieval-Augmented Generation) jurídico com compressão observável de embeddings. A arquitetura segue os princípios de Clean Architecture (Robert C. Martin), com separação rígida em quatro camadas e inversão de dependência em todas as fronteiras.

```
┌─────────────────────────────────────────────────┐
│               Presentation Layer                │
│   FastAPI (REST) · Jinja2+HTMX (Web SSR)        │
├─────────────────────────────────────────────────┤
│               Application Layer                 │
│   Use Cases · DTOs de entrada/saída             │
├─────────────────────────────────────────────────┤
│                 Domain Layer                    │
│   Entities · Value Objects · Interfaces         │
├─────────────────────────────────────────────────┤
│             Infrastructure Layer               │
│   PostgreSQL · ChromaDB · HuggingFace · Ollama  │
└─────────────────────────────────────────────────┘
```

A regra de dependência é unidirecional: camadas externas dependem das internas. O domínio não importa nada das outras camadas.

---

## 2. Stack tecnológico

| Componente        | Tecnologia                       | Versão                        |
| ----------------- | -------------------------------- | ----------------------------- |
| Runtime           | Python                           | 3.12                          |
| Framework web     | FastAPI                          | 0.115+                        |
| ORM               | SQLAlchemy                       | 2.0                           |
| Banco relacional  | PostgreSQL                       | 16                            |
| Vector store      | ChromaDB                         | local persistido              |
| Embedding local   | sentence-transformers (E5-small) | via HuggingFace               |
| LLM local         | Ollama (qwen2.5:7b)              | API REST                      |
| LLM remoto        | OpenAI API                       | gpt-4o-mini                   |
| Frontend          | Jinja2 + HTMX + Tailwind CDN     | SSR                           |
| Autenticação      | JWT (python-jose) + bcrypt       | cookie HttpOnly               |
| Migrations        | Alembic                          | head = 0007                   |
| CI/CD             | GitHub Actions                   | ruff · mypy · bandit · pytest |
| Gestão de pacotes | uv                               | lockfile                      |

---

## 3. Camadas e responsabilidades

### 3.1 Domain Layer (`src/docuvector/domain/`)

Núcleo do sistema. Não possui dependências externas.

**Entidades principais:**
- `Document` — documento indexado com status, checksum e metadados de compressão
- `DocumentChunk` — fragmento de texto com embedding_provider e chunk_index
- `User` — usuário com role (admin/user) e hash de senha
- `AuditEvent` — evento imutável de ledger de auditoria
- `CompressionMetrics` — resultado de benchmark: retention, savings, dims

**Interfaces (Protocols):**
- `VectorStore` — `add_chunks`, `search`, `get_vectors_for_document`, `delete_document`
- `DocumentRepository` — CRUD + `list_chunks_for_document`
- `EmbeddingProvider` — `embed_query`, `embed_passages`
- `LlmClient` — `generate`
- `AuditRepository` — `append`
- `Compressor` — `fit`, `transform`

**Enums:**
- `CompressionMethod` — PCA, RANDOM_PROJECTION, INT8, BINARY
- `EmbeddingProviderName`, `LlmProviderName`, `UserRole`, `AuditAction`

### 3.2 Application Layer (`src/docuvector/application/`)

Orquestra os casos de uso. Depende apenas de interfaces do domínio.

| Use Case                             | Responsabilidade                            |
| ------------------------------------ | ------------------------------------------- |
| `IngestionUseCase`                   | extract → split → embed → store + audit     |
| `MultiCollectionIngestionUseCase`    | ingestão + replicação nas 5 coleções Chroma |
| `RetrievalUseCase`                   | busca semântica com threshold               |
| `AnswerUseCase`                      | retrieval + geração LLM + audit             |
| `CompressionBenchmarkUseCase`        | benchmark dos 4 compressores sem persistir  |
| `CompressToCollectionUseCase`        | compressão + persistência na coleção alvo   |
| `CompareRetrievalUseCase`            | Recall@K, Precision@K, MRR entre coleções   |
| `EmbeddingBenchmarkUseCase`          | latência e custo por embedding provider     |
| `MetricsUseCase`                     | agregação de métricas operacionais          |
| `AuthUseCase`, `RegisterUserUseCase` | autenticação e registro                     |
| `AdminUserManagementUseCase`         | CRUD de usuários (role=admin)               |

### 3.3 Infrastructure Layer (`src/docuvector/infrastructure/`)

Implementações concretas das interfaces do domínio.

**Vector stores:**
- `ChromaVectorStore` — store original float32
- `CompressedVectorStore` — wrapper que comprime antes de indexar (Int8, Binary, RP)
- `CorpusPcaStore` — PCA global treinado no corpus completo, fit explícito

**Compressores:**
- `Int8Compressor` — quantização 4x (float32 → int8)
- `BinaryCompressor` — quantização 32x (float32 → uint8 packbits)
- `PcaCompressor` — redução de dimensão via SVD
- `RandomProjectionCompressor` — projeção gaussiana aleatória (seed fixo = 42)

**Embeddings:**
- `SentenceTransformersEmbedder` — E5-small local, sem custo
- `OpenAIEmbedder` — text-embedding-ada-002, com custo rastreado

**LLM:**
- `MockLlmClient` — resposta determinística para testes
- `OllamaLlmClient` — qwen2.5:7b via API REST local
- `OpenAILlmClient` — gpt-4o-mini com contagem de tokens e custo

**Persistência:**
- `SqlAlchemyDocumentRepository` — PostgreSQL via SQLAlchemy 2.0
- `SqlAlchemyAuditRepository` — ledger append-only
- `SqlAlchemyUserRepository` — com find_by_email, find_by_id

### 3.4 Presentation Layer

**REST API** (`src/docuvector/api/routers/`):
- `/api/v1/auth/` — login, registro, refresh
- `/api/v1/documents/` — upload, list, delete, compress, benchmark
- `/api/v1/queries/` — ask
- `/api/v1/metrics/` — dashboard, benchmark de embeddings
- `/api/v1/admin/users/` — CRUD de usuários

**Web SSR** (`src/docuvector/api/web/`):
- `/app/chat` — consulta principal com seletor de coleção e A/B compare
- `/app/dashboard` — métricas operacionais, saúde do corpus, comparação IR
- `/app/admin` — painel de administração

**Injeção de dependências** (`src/docuvector/api/deps.py`):
- Factories com `@lru_cache` para singletons de stores e services
- `StoreEntry = tuple[CompressionMethod, VectorStore]` como tipo canônico
- `resolve_vector_store_by_collection()` — padrão Strategy por request

---

## 4. Múltiplas coleções Chroma

O sistema mantém 5 coleções ChromaDB em paralelo:

| Coleção             | Tipo    | Dimensões | Bytes/vetor |
| ------------------- | ------- | --------- | ----------- |
| `docuvector`        | float32 | 384       | 1536 B      |
| `docuvector_int8`   | int8    | 384       | 384 B       |
| `docuvector_binary` | uint8   | 384       | 48 B        |
| `docuvector_pca`    | float32 | 192       | 768 B       |
| `docuvector_rp`     | float32 | 192       | 768 B       |

Fluxo de ingestão:
```
Upload
  └── IngestionUseCase (coleção original)
        └── MultiCollectionIngestionUseCase
              ├── add_chunks → docuvector_int8
              ├── add_chunks → docuvector_binary
              ├── add_chunks → docuvector_rp
              └── add_chunks + fit_corpus() → docuvector_pca
```

---

## 5. Segurança

Defesas implementadas documentadas em `docs/SECURITY_THREAT_MODEL.md`.

**Principais controles:**
- JWT em cookie `HttpOnly` (não acessível via JS)
- BOLA: todas as queries filtram por `owner_id` antes de retornar dados
- Bcrypt com rounds configurável (12 prod, 4 test)
- Validação de senha via política NIST SP 800-63B
- Rate limiting via `slowapi` (shared_limiter)
- SAST: bandit, ruff (strict), mypy (strict)
- SCA: pip-audit + gitleaks + CycloneDX SBOM
- Inputs sanitizados: tamanho máximo de upload configurável

---

## 6. Banco de dados

Schema PostgreSQL com 5 tabelas principais:

```
users ──< documents ──< document_chunks
                    └── (compressão via campos nullable)
audit_logs (append-only, sem FK para preservar ledger)
```

Migrations Alembic (`migrations/versions/`):
- `0001` — schema inicial
- `0002` — CITEXT para email case-insensitive
- `0003` — documents + chunks
- `0004` — extensão do enum audit_action
- `0005` — decoupling do ledger de auditoria
- `0006` — campos de compressão nullable
- `0007` — audit actions da Sprint 6

---

## 7. Configuração

Todas as configurações via variáveis de ambiente (arquivo `.env`).
Ver `docs/.env.example` para lista completa.

Principais grupos:
- `APP_*` — host, porta, ambiente, secret JWT
- `DATABASE_URL` — connection string PostgreSQL
- `CHROMA_*` — diretório de persistência e nomes de coleção
- `SEED_ADMIN_*` — credenciais do admin bootstrap
- `OPENAI_*` — API key e modelos
- `OLLAMA_*` — base URL e modelo
- `RAG_*` — top_k, similarity_threshold, chunk_size

---

## 8. Decisões de design registradas

| ID      | Decisão                                                  | Alternativa rejeitada       | Motivo                                              |
| ------- | -------------------------------------------------------- | --------------------------- | --------------------------------------------------- |
| ADR-001 | Protocol para VectorStore (structural subtyping)         | ABC/herança                 | Sem acoplamento, testável com fakes simples         |
| ADR-002 | PCA global via CorpusPcaStore (fit explícito)            | PCA por documento           | PCA por doc gera espaços vetoriais incomparáveis    |
| ADR-003 | Ground truth = coleção original para Recall@K            | Anotação humana             | Scope TCC; defensável como "fidelidade ao baseline" |
| ADR-004 | Texto preservado nas coleções comprimidas via PostgreSQL | Reindexar apenas embeddings | Sem texto: RAG falha (LLM sem contexto)             |
| ADR-005 | Delete antes de add_chunks (idempotência forte)          | UUID novo por compressão    | Evita duplicação silenciosa no ChromaDB             |
| ADR-006 | Seed do admin no lifespan da aplicação                   | Script manual               | Elimina ForeignKeyViolation após reset do banco     |
| ADR-007 | Cookie HttpOnly para JWT no frontend                     | Header Authorization        | Sem acesso JS, proteção contra XSS                  |
