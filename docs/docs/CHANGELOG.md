# CHANGELOG — JurisVector

Todas as mudanças relevantes são documentadas aqui.
Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).
Versionamento: [Semantic Versioning](https://semver.org/).

---

## [1.0.0] — Junho 2026

### Adicionado
- **Sprint 6**: 5 coleções ChromaDB paralelas (original, int8, binary, pca, rp)
- `CompressedVectorStore`: wrapper de compressão sobre VectorStore Protocol
- `CorpusPcaStore`: PCA global com `fit_corpus()` explícito
- `MultiCollectionIngestionUseCase`: ingestão + replicação em 4 coleções comprimidas
- `CompareRetrievalUseCase`: métricas IR (Recall@K, Precision@K, MRR)
- `CompressToCollectionUseCase`: compressão sob demanda com persistência
- Seletor de coleção no chat com badges visuais
- Comparação A/B de respostas entre duas coleções
- Botões de análise contextual inline por mensagem de chat
- Menu dropdown por documento para compressão sob demanda
- Badge de confiança calibrado na resposta (Alta / Parcial / Fraca)
- Seed automático do admin no lifespan da aplicação
- Validação de existência do usuário no banco (previne ForeignKeyViolation)
- Dashboard redesenhado com cards visuais e seção de saúde do corpus
- Migration `0007`: audit actions Sprint 6
- Collection names configuráveis via environment variables

### Corrigido
- Recall@K > 100%: deduplicação de document_ids antes do cálculo
- Texto vazio nas coleções comprimidas: texto recuperado do PostgreSQL
- Duplicação no ChromaDB: `delete_document` antes de `add_chunks`
- `functools.lru_cache` → `@lru_cache` (padrão do projeto)
- `require_authenticated_user`: sessão inválida após reset do banco retorna 401 limpo

---

## [0.6.0] — Junho 2026

### Adicionado
- **Sprint 5**: frontend JurisVector com Jinja2 + HTMX + Tailwind
- JWT em cookie `HttpOnly` no frontend
- Queries predefinidas clicáveis (sem auto-submit)
- Histórico de chat no `sessionStorage`
- Painel de comparação de coleções expansível
- Admin panel com gestão de usuários

---

## [0.4.0] — Maio/Junho 2026

### Adicionado
- **Sprint 4B**: dashboard de métricas operacionais
- `EmbeddingBenchmarkUseCase`: latência, custo, tamanho por provider
- `MetricsUseCase`: storage savings, estimativa Pinecone/Qdrant
- Migrations `0004` e `0005`: ledger de auditoria decoupled

### Adicionado (Sprint 4A)
- Entidade `CompressionMetrics`
- 4 compressores: Int8, Binary, PCA, RandomProjection
- `CompressionBenchmarkUseCase`
- Retenção semântica via Pearson de matrizes coseno
- Migration `0006`: campos de compressão nullable

---

## [0.3.0] — Maio 2026

### Adicionado
- **Sprint 3**: pipeline RAG completo
- Extractors: PDF, TXT, detecção automática
- `RecursiveSplitter` configurável
- `SentenceTransformersEmbedder` (E5-small local)
- `OpenAIEmbedder` com rastreamento de custo
- `ChromaVectorStore` com BOLA em todas as operações
- `IngestionUseCase`, `RetrievalUseCase`, `AnswerUseCase`
- `MockLlmClient`, `OllamaLlmClient`
- Migration `0003`: documents + chunks

---

## [0.2.0] — Maio 2026

### Adicionado
- **Sprint 2**: autenticação multi-tenant
- JWT + bcrypt + política NIST SP 800-63B
- RBAC: admin / user
- CRUD de documentos com isolamento por owner_id
- Seed do admin via variáveis de ambiente
- Migrations `0002` (CITEXT) e `0003` (documents)

### Corrigido
- INC-001: `flush()` sem `commit()` causava perda de dados no registro
- INC-002: drift entre ORM e schema PostgreSQL
- INC-003: `Depends` override ignorado em testes de integração

---

## [0.1.0] — Maio 2026

### Adicionado
- **Sprint 1**: fundação do projeto
- Clean Architecture (4 camadas)
- FastAPI com lifespan, exception handlers, rate limiting
- PostgreSQL em Docker + Alembic
- GitHub Actions CI: ruff, mypy, bandit, pytest, pip-audit
- `just` como task runner
- Health check
