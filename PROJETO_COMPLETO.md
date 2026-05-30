# DocuVector Lite — Documento Mestre do Projeto

> **Trabalho final da disciplina de Desenvolvimento de Sistemas — CEUB**
> Sistema RAG aplicado a documentos jurídicos com compressão observável de embeddings e benchmark de provedores.

**Versão:** 1.0
**Data:** 25/05/2026
**Autor:** Davi Rosa F.
**Janela de execução:** 14 dias
**Status:** Sprint 1 concluída

---

## Índice

1. Sumário executivo
2. Problema, solução e diferencial
3. Decisões arquiteturais fundamentais
4. Stack tecnológica completa
5. Arquitetura em camadas (Clean Architecture)
6. Mapa de pastas e responsabilidades por arquivo
7. Fluxos do sistema (passo a passo)
8. Modelo de dados (relacional + vetorial)
9. Segurança e DevSecOps em profundidade
10. Pipeline CI/CD completo
11. Plano por sprint (8 sprints, 14 dias)
12. Checklist de implementação por sprint
13. Estratégia de testes
14. Roteiro de apresentação (10 minutos)
15. Glossário técnico
16. FAQ defensivo (perguntas que a banca pode fazer)
17. Referências bibliográficas

---

## 1. Sumário executivo

DocuVector Lite é um portal web para advogados, escritórios e estudantes de Direito enviarem documentos jurídicos (contratos, peças, jurisprudência) e consultá-los em linguagem natural com respostas fundamentadas nos próprios documentos. O sistema demonstra de forma observável duas decisões arquiteturais que normalmente ficam invisíveis em RAGs didáticos: **a compressão de embeddings** (quatro algoritmos comparados lado a lado) e a **escolha de provedor de embedding** (OpenAI remoto vs Sentence Transformers local, com cronometragem em tempo real).

O produto atende integralmente aos requisitos do edital (BRD, SRS, diagramas, autenticação segura, CRUD completo, Swagger, ORM, banco em Docker, testes automatizados, Clean Architecture) e adiciona um conjunto incomum de práticas DevSecOps para um trabalho acadêmico: SAST (Bandit), SCA (pip-audit), detecção de segredos (detect-secrets), SBOM em CycloneDX, threat model formal (STRIDE + OWASP API Top 10 + NIST SSDF), tipagem estrita (mypy), e pipeline CI no GitHub Actions.

O contexto temático é jurídico. O texto da UI, os exemplos, o prompt template do LLM e o vocabulário das telas refletem o domínio (contratos, cláusulas, partes, peças, jurisprudência), o que diferencia o produto de uma demonstração genérica de RAG.

---

## 2. Problema, solução e diferencial

### 2.1 O problema

Profissionais do Direito lidam com volume crescente de documentos textuais. Localizar uma cláusula específica, comparar contratos, encontrar trechos de jurisprudência aplicável ou responder dúvidas factuais sobre uma peça exige hoje leitura linear ou busca por palavra-chave, ambas ineficientes em corpus grandes ou em linguagem complexa.

Sistemas de **Retrieval-Augmented Generation (RAG)** resolvem essa busca semântica transformando o texto em representações vetoriais (embeddings) e recuperando trechos por similaridade matemática. Mas três custos ficam escondidos em RAGs didáticos:

| Custo escondido | Explicação |
|---|---|
| **Memória dos embeddings** | Cada chunk vira um vetor de centenas ou milhares de floats de 32 bits. Em corpus grandes, isso vira gigabytes de RAM. |
| **Custo financeiro do provedor** | Provedores como OpenAI cobram por token. Indexar 1000 documentos pode custar dezenas de dólares. |
| **Trade-off qualidade vs privacidade** | Embedders remotos podem ser melhores, mas mandam o conteúdo do documento para terceiros. |

### 2.2 A solução

DocuVector Lite faz o pipeline RAG completo e expõe esses três custos no front. O usuário não apenas consulta seus documentos: ele **vê** quanto custou indexar, quanto economizou comprimindo, e qual o impacto da compressão na qualidade da resposta.

### 2.3 O diferencial técnico (o que tira nota)

Quatro pilares de valor mensurável:

1. **Compressão de embeddings comparativa.** PCA, Random Projection, Quantização Int8 e Quantização Binária aplicados sobre os mesmos embeddings do usuário, com métricas calculadas: dimensão antes/depois, ratio em bytes, RAM real ocupada, retenção semântica via correlação de Pearson, tempos de fit e transform.
2. **Comparação de embedders em tempo real.** Mesma pergunta executada via OpenAI e via modelo local E5, com tempo de embedding, tempo de busca e custo estimado em USD para cada chamada.
3. **DevSecOps acadêmico real.** SAST, SCA, secrets, SBOM, threat model STRIDE + OWASP + NIST. Cobre o que governos hoje exigem de fornecedores de software.
4. **Tematização jurídica.** Toda a UI, copy, exemplos e prompt template falam a linguagem do operador do Direito, não a linguagem do engenheiro de dados.

### 2.4 O diferencial pedagógico

A construção do sistema é parte da avaliação. O documento de evidências mostra **processo**, não apenas produto: como o escopo foi congelado, como as decisões foram tomadas, como o pipeline DevSecOps capturou vulnerabilidades reais e como elas foram mitigadas com rastreabilidade.

---

## 3. Decisões arquiteturais fundamentais

Cada decisão abaixo foi tomada de forma deliberada e tem justificativa defensável diante de uma banca. A regra do projeto é: **se você não consegue defender, não faz parte do projeto**.

### 3.1 Linguagem: Python 3.11

**Decisão:** Python 3.11.
**Alternativas consideradas:** C# / .NET (preferência do edital), Go, Node.js + TypeScript.
**Por quê:** O ecossistema de embeddings, vetores e modelos de linguagem é nativo em Python (Sentence Transformers, OpenAI SDK, ChromaDB). Tentar fazer RAG em C# obrigaria a chamar Python via subprocess ou usar ONNX, o que adiciona complexidade não relacionada ao escopo. Python 3.11 traz melhorias de performance (10-60% mais rápido que 3.10) e tipagem mais expressiva.
**Trade-off:** Perdemos a preferência declarada do edital. Compensamos com qualidade técnica acima do baseline em outras dimensões.

### 3.2 Framework web: FastAPI

**Decisão:** FastAPI.
**Alternativas consideradas:** Django + DRF, Flask, Litestar.
**Por quê:**
- Geração automática de Swagger/OpenAPI 3.1 a partir dos schemas Pydantic. O edital exige Swagger; FastAPI entrega de graça.
- Validação de entrada com Pydantic v2 elimina código repetitivo.
- Async nativo: importante para benchmarks cronometrados confiáveis (sem bloqueio de event loop entre embed local e chamada de rede).
- Dependency injection nativa permite implementar Clean Architecture sem framework adicional.
- Menor superfície que Django (Django tem auth, ORM, admin embutidos que vão duplicar o que vamos construir).
**Trade-off:** FastAPI é mais novo, sofre advisories ocasionais (vide MAL-2026-4750 que o pip-audit detectou e mitigamos com decisão documentada).

### 3.3 ORM: SQLAlchemy 2.0

**Decisão:** SQLAlchemy 2.0 + Alembic.
**Alternativas consideradas:** Django ORM, Tortoise ORM, raw SQL via psycopg.
**Por quê:**
- Padrão do mercado Python para sistemas que precisam de queries complexas.
- API 2.0 (com `Mapped[]` e tipagem) integra bem com mypy strict.
- Alembic é o padrão de fato para migrations em ecossistema SQLAlchemy.
- O edital exige ORM; SQLAlchemy é o ORM mais respeitado em Python.
**Como usado:** Modelos ORM ficam isolados em `infrastructure/persistence/models.py`. Repositórios (que o domínio enxerga) traduzem ORM ⇄ entidades de domínio puras. O domínio nunca importa SQLAlchemy.

### 3.4 Vector store: ChromaDB

**Decisão:** ChromaDB com `PersistentClient`.
**Alternativas consideradas:** FAISS direto, Qdrant em Docker, pgvector (extensão Postgres).
**Por quê:**
- Já estava na base original do autor.
- Interface Python clara e tipada.
- Persistência local em arquivo, sem necessidade de outro container.
- Suporta filtros por metadata (essencial para isolamento multi-tenant: filtramos por `owner_id` em toda busca).
**Trade-off:** ChromaDB é mais novo que FAISS, mas a abstração `VectorStore` no domínio permite trocar sem reescrever use cases.

### 3.5 Sem framework RAG (decisão de design crítica)

**Decisão:** Stack raw. Sem LangChain, sem LlamaIndex, sem Haystack.
**Por quê:**
- LangChain abstrai exatamente o que queremos demonstrar (extração, chunking, embedding, retrieval). Esconder isso seria esconder a engenharia do projeto.
- Reduz dependências de ~115 (com LangChain) para ~25.
- Bandit e pip-audit ficam limpos (LangChain tem histórico de advisories de prompt injection e SSRF).
- Auditável: cada linha do pipeline é explícita e tipada.
- Defensável: "tirei o framework e implementei o pipeline na mão" pesa positivo em uma banca de engenharia.
**Trade-off:** Mais código escrito por nós. Compensado pela clareza pedagógica.

### 3.6 Front-end server-side (Jinja2 + HTMX)

**Decisão:** Jinja2 + HTMX + Tailwind via CDN.
**Alternativas consideradas:** React + Vite, Vue, Svelte.
**Por quê:**
- Zero build step npm. Sem node_modules. Reduz superfície de ataque do supply chain.
- Renderização server-side é o padrão clássico de aplicações jurídicas (e nossa UI é jurídica).
- HTMX permite interatividade rica (upload com progresso, comparação em tempo real, troca de painel sem reload) com 15 KB de JavaScript.
- Tipo de UI esperado pelo usuário-alvo (advogados) prefere telas densas de informação, não SPAs animadas.
**Trade-off:** Sem state management cliente complexo. Para benchmarks em tempo real, isso obrigaria HTMX polling, que cobre 100% do nosso caso.

### 3.7 Embedders: dois, intercambiáveis

**Decisão:** `text-embedding-3-small` (OpenAI) e `intfloat/multilingual-e5-small` (local).
**Por quê:**
- OpenAI: padrão de mercado, qualidade alta, custo por token.
- E5 multilíngue: forte em PT-BR (treinado em mC4 incluindo português), 384 dimensões para comparação justa, gratuito após download dos pesos (~470 MB).
- Mesma dimensão facilita visualização do trade-off.
**Restrição operacional:** Modelo E5 exige prefixos textuais (`"query: "` para consultas, `"passage: "` para indexação). Esse detalhe é encapsulado no provider e não vaza para a camada de aplicação.

### 3.8 Compressores: quatro, com semânticas diferentes

**Decisão:** PCA, Random Projection, Quantização Int8, Quantização Binária.

| Compressor | Tipo | Trade-off didático |
|---|---|---|
| PCA | Redução de dimensionalidade linear | Determinística, preserva variância, exige fit em batch |
| Random Projection | Redução de dimensionalidade aleatória | Baseada em Johnson-Lindenstrauss, sem fit, mais rápida |
| Int8 | Quantização sem redução de dimensão | Reduz 4x a RAM, preserva quase toda a qualidade |
| Binary | Quantização extrema | Reduz 32x a RAM, perda de qualidade visível |

Quatro algoritmos cobrem o espectro: dimensão vs precisão numérica vs tempo vs RAM.

### 3.9 LLM: OpenAI gpt-4o-mini

**Decisão:** `gpt-4o-mini` via API.
**Por quê:** Custo extremamente baixo (USD 0.15/1M tokens input), suporte nativo a sistema/usuário, latência baixa.
**Alternativa para futuro:** Ollama local. Fora do escopo da v1.0 por restrição de tempo.

### 3.10 Gerenciador de dependências: uv

**Decisão:** `uv` em vez de `pip` + `venv`.
**Por quê:** 10-100x mais rápido, lock file determinístico, instala Python automaticamente, integra com `pyproject.toml`. É o padrão emergente em projetos Python sérios em 2026.

### 3.11 Resolução de erros do pip-audit no Windows

**Decisão:** `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` no `justfile`.
**Por quê:** Bug conhecido do `pip-api` em caminhos não-ASCII no Windows (ex: `Área de Trabalho`). Forçar UTF-8 em todos os subprocessos resolve. Mover o projeto para `C:\dev\` ajuda também, mas a variável de ambiente é a cura permanente.

---

## 4. Stack tecnológica completa

Para cada tecnologia, explicamos: **o que faz**, **por que escolhemos**, **alternativas consideradas**, **onde aparece no projeto**.

### 4.1 Camada de aplicação

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **FastAPI** | 0.136.3 | Framework web ASGI; roteamento HTTP; geração automática de OpenAPI | Flask, Django + DRF, Litestar | `src/docuvector/api/`, `main.py` |
| **Uvicorn** | 0.30+ | Servidor ASGI de produção; serve a aplicação FastAPI | Hypercorn, Daphne | comando `just dev` |
| **Pydantic** | 2.7+ | Validação de dados, schemas, settings; tipagem forte em runtime | Marshmallow, attrs | Todos os schemas em `api/schemas/`, settings, schemas de domínio |
| **Pydantic Settings** | 2.4+ | Validação de variáveis de ambiente com tipos | python-decouple, dynaconf | `src/docuvector/config/settings.py` |
| **SlowAPI** | 0.1.9+ | Rate limit declarativo via decorators | starlette-limiter | Middleware em `/auth/login` |
| **Jinja2** | 3.1+ | Template engine server-side | Mako, Chameleon | `src/docuvector/web/templates/` |
| **python-multipart** | 0.0.9+ | Parse de uploads multipart/form-data | n/a (necessário para FastAPI uploads) | Endpoint de upload |

### 4.2 Persistência

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **SQLAlchemy** | 2.0+ | ORM relacional, queries tipadas | Django ORM, Tortoise, raw SQL | `infrastructure/persistence/` |
| **Alembic** | 1.13+ | Migrations versionadas | Yoyo, raw SQL | `migrations/` |
| **psycopg (v3)** | 3.2+ | Driver PostgreSQL nativo | psycopg2, asyncpg | Driver no `DATABASE_URL` |
| **PostgreSQL** | 16-alpine | Banco relacional principal | MySQL, SQLite | Container Docker, `docker/docker-compose.yml` |
| **ChromaDB** | 0.5+ | Vector store persistente | FAISS, Qdrant, pgvector | `infrastructure/vector/chroma_vector_store.py` |

### 4.3 Segurança

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **passlib[bcrypt]** | 1.7+ | Hash de senha resistente a brute force | argon2-cffi (mais moderno) | `infrastructure/security/bcrypt_hasher.py` |
| **python-jose** | 3.3+ | Geração e verificação de JWT | PyJWT, authlib | `infrastructure/security/jwt_service.py` |
| **detect-secrets** | 1.5+ | SAST de segredos em código | gitleaks, trufflehog | Pre-commit hook |
| **Bandit** | 1.7+ | SAST de código Python | semgrep | Pre-commit + CI |
| **pip-audit** | 2.7+ | SCA via OSV.dev | safety (comercial), snyk (comercial) | CI + `just sca` |
| **cyclonedx-bom** | 4.4+ | Geração de SBOM em formato CycloneDX | syft | CI artifact |

### 4.4 Embeddings e IA

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **sentence-transformers** | 5.0+ | Embeddings locais via modelos HuggingFace | direct transformers | `infrastructure/embeddings/sentence_transformers_provider.py` |
| **transformers (HF)** | 5.0+ | Carrega modelos do HuggingFace Hub | n/a (dep de sentence-transformers) | Indireto |
| **openai** | 1.40+ | SDK oficial para embeddings remotos e LLM | httpx direto | `infrastructure/embeddings/openai_provider.py`, LLM client |
| **numpy** | 1.26+ | Matemática vetorial; arrays de embeddings | n/a (padrão de fato) | Toda a camada de compressão |
| **scikit-learn** | 1.5+ | PCA, Random Projection, métricas | scipy, manual | `infrastructure/compression/pca_compressor.py`, `random_projection_compressor.py` |
| **scipy** | 1.13+ | Pearson correlation para retenção semântica | manual | `application/compression_benchmark_use_case.py` |

### 4.5 Extração de documentos

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **pypdf** | 6.10.2+ | Extração de texto de PDF | pdfplumber, pdfminer | `infrastructure/extraction/pypdf_extractor.py` |

### 4.6 Observabilidade

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **structlog** | 24.4+ | Logging estruturado em JSON | python-json-logger, loguru | `infrastructure/logging/structlog_config.py` |

### 4.7 Qualidade de código

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **ruff** | 0.6+ | Lint + formatter (substitui flake8, black, isort, pylint) | combinação dos clássicos | `pyproject.toml`, pre-commit, CI |
| **mypy** | 1.11+ | Tipagem estática strict | pyright, pyre | `pyproject.toml`, pre-commit, CI |
| **pytest** | 9.0+ | Framework de testes | unittest, nose2 | `tests/` |
| **pytest-cov** | 5.0+ | Cobertura de código (gate 70%) | coverage direto | CI |
| **pytest-asyncio** | 1.0+ | Testar funções async | n/a (padrão) | `tests/conftest.py` |
| **hypothesis** | 6.110+ | Testes baseados em propriedades | n/a | Testes de compressão |

### 4.8 Infra e automação

| Tecnologia | Versão | Função | Alternativas | Onde aparece |
|---|---|---|---|---|
| **uv** | 0.4+ | Gerenciador de dependências e venv | pip + venv, poetry, pdm | `just sync`, CI |
| **Docker** | 20+ | Containerização | Podman | `docker/docker-compose.yml` |
| **Docker Compose** | v2 | Orquestração multi-container | k8s (overkill) | `docker/docker-compose.yml` |
| **just** | 1.30+ | Task runner declarativo | make, npm scripts | `justfile` |
| **pre-commit** | 3.8+ | Hooks Git para qualidade local | husky (Node), lefthook | `.pre-commit-config.yaml` |
| **GitHub Actions** | n/a | CI/CD | GitLab CI, Jenkins | `.github/workflows/ci.yml` |

---

## 5. Arquitetura em camadas (Clean Architecture)

### 5.1 Princípio fundamental

**Clean Architecture, formulada por Robert C. Martin (Uncle Bob)**, organiza o código em camadas concêntricas. A única regra obrigatória é a **Regra de Dependência (Dependency Rule)**: dependências de código apontam apenas para dentro. Camadas externas conhecem camadas internas; o inverso é proibido.

```
┌─────────────────────────────────────────────────┐
│  APRESENTAÇÃO (api, web)                        │  ← FastAPI, Jinja2
│  ┌───────────────────────────────────────────┐  │
│  │  INFRAESTRUTURA                           │  │  ← SQLAlchemy, Chroma, OpenAI
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  APLICAÇÃO (use cases)              │  │  │  ← orquestração
│  │  │  ┌───────────────────────────────┐  │  │  │
│  │  │  │  DOMÍNIO (entidades + interf) │  │  │  │  ← puro, sem deps
│  │  │  └───────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 5.2 As quatro camadas

#### Camada 1 — Domínio (`src/docuvector/domain/`)

**O que tem aqui:**
- Entidades puras de negócio: `User`, `Document`, `Chunk`, `QueryRecord`, `CompressionResult`.
- Interfaces (abstrações) que a aplicação consome: `UserRepository`, `DocumentRepository`, `VectorStore`, `EmbeddingProvider`, `Compressor`, `DocumentExtractor`, `TextSplitter`, `PasswordHasher`, `TokenService`, `AuditRepository`.
- Exceções de domínio: `DocumentNotFound`, `UnauthorizedAccess`, `EmptyDocumentError`.
- Enums: `UserRole`, `FileFormat`, `DocumentStatus`, `ProviderName`, `CompressionMethod`.

**O que NUNCA tem aqui:**
- Import de FastAPI.
- Import de SQLAlchemy.
- Import de ChromaDB, OpenAI, Sentence Transformers.
- Conhecimento de HTTP, JSON, banco de dados.

**Por que isso importa:** O domínio é a parte mais estável do sistema. Se trocarmos Chroma por Qdrant, FastAPI por Litestar, Postgres por MySQL: **o domínio não muda uma linha**.

#### Camada 2 — Aplicação (`src/docuvector/application/`)

**O que tem aqui:**
- Use cases (casos de uso): classes com um único método público `execute()` ou similar.
- Cada use case orquestra entidades e interfaces do domínio para atender a uma intenção do usuário.

**Use cases planejados:**
- `AuthUseCase` — login e me
- `DocumentCrudUseCase` — list, get, update, delete
- `IngestionUseCase` — upload, extract, chunk, embed, opcionalmente comprimir, persist
- `RetrievalUseCase` — embed query, search, threshold
- `AnswerUseCase` — retrieval + LLM
- `CompressionBenchmarkUseCase` — 4 compressores + métricas
- `EmbeddingBenchmarkUseCase` — dois providers + comparação
- `MetricsUseCase` — agregação para o dashboard

**Princípio:** Cada use case recebe suas dependências (interfaces de domínio) via construtor. Isso satisfaz **Dependency Inversion (D do SOLID)** e permite testabilidade total com mocks.

#### Camada 3 — Infraestrutura (`src/docuvector/infrastructure/`)

**O que tem aqui:**
- Implementações concretas das interfaces de domínio.
- Toda a integração com mundo externo: banco, vector store, embedders, LLM, filesystem, criptografia, logging.

**Mapeamento interface → implementação:**

| Interface (domínio) | Implementação (infra) |
|---|---|
| `UserRepository` | `SqlAlchemyUserRepository` |
| `DocumentRepository` | `SqlAlchemyDocumentRepository` |
| `AuditRepository` | `SqlAlchemyAuditRepository` |
| `VectorStore` | `ChromaVectorStore` |
| `EmbeddingProvider` | `OpenAIEmbeddingProvider`, `SentenceTransformersEmbeddingProvider` |
| `Compressor` | `PcaCompressor`, `RandomProjectionCompressor`, `Int8Compressor`, `BinaryCompressor` |
| `DocumentExtractor` | `PyPdfExtractor`, `TxtExtractor`, `MdExtractor` |
| `TextSplitter` | `RecursiveSplitter` |
| `PasswordHasher` | `BcryptPasswordHasher` |
| `TokenService` | `JwtTokenService` |

#### Camada 4 — Apresentação (`src/docuvector/api/` e `src/docuvector/web/`)

**O que tem aqui:**
- Routers FastAPI (HTTP).
- Schemas Pydantic de request/response (formato wire).
- Middlewares (autenticação, rate limit, audit).
- Templates Jinja2 (front HTML).
- Dependency providers (montam use cases com injeção concreta).

**Princípio:** Routers **traduzem** HTTP para chamadas de use case. Não contêm regra de negócio. Se um router está calculando algo, é bug arquitetural.

### 5.3 Por que isso responde ao SOLID

| Princípio SOLID | Como o projeto satisfaz |
|---|---|
| **S — Single Responsibility** | Cada classe (entidade, use case, repositório, compressor) tem uma única razão para mudar. |
| **O — Open/Closed** | Adicionar um novo compressor (ex: Product Quantization) é criar nova classe implementando `Compressor`, sem tocar nas existentes. |
| **L — Liskov** | Qualquer implementação de `EmbeddingProvider` pode substituir outra; o use case não percebe. |
| **I — Interface Segregation** | Interfaces pequenas e específicas (`Compressor` não tem método de persistência; `VectorStore` não tem método de extração). |
| **D — Dependency Inversion** | Use cases dependem de abstrações (interfaces de domínio), não de concreções (SQLAlchemy, Chroma). |

### 5.4 Por que isso responde ao "tira nota" da banca

A frase de defesa é:

> "Construí o sistema seguindo Clean Architecture de Robert C. Martin. O domínio é puro Python, sem dependências externas. A aplicação orquestra via interfaces. A infraestrutura implementa concretamente. A apresentação só traduz HTTP. Isso me permite trocar qualquer peça externa sem reescrever a lógica de negócio, e me permite testar cada camada isoladamente."

---

## 6. Mapa de pastas e responsabilidades por arquivo

### 6.1 Visão geral

```
docuvector-lite/
├── .github/workflows/        # CI/CD GitHub Actions
├── docker/                   # Stack de containers (Postgres)
├── docs/                     # Documentação acadêmica completa
├── src/docuvector/           # Código-fonte (4 camadas)
├── tests/                    # Testes automatizados
├── migrations/               # Migrations Alembic
├── scripts/                  # Scripts utilitários (seed)
├── data/                     # Persistência local (ChromaDB, HF cache)
└── (arquivos raiz)           # pyproject, justfile, .env, .gitignore, ...
```

### 6.2 Responsabilidade por arquivo (essencial)

#### Raiz do projeto

| Arquivo | Função |
|---|---|
| `pyproject.toml` | Define dependências, scripts, configurações de ruff/mypy/bandit/pytest |
| `justfile` | Receitas de tarefas locais (just sync, just ci, just up, just dev) |
| `.pre-commit-config.yaml` | Hooks que rodam antes de cada commit |
| `.env.example` | Template de variáveis de ambiente; vai para o Git |
| `.env` | Variáveis de ambiente reais; **nunca vai para o Git** |
| `.gitignore` | Arquivos ignorados pelo Git |
| `.pip-audit.toml` | Allowlist documentada de CVEs aceitos como risco residual |
| `.secrets.baseline` | Baseline do detect-secrets (falsos positivos conhecidos) |
| `alembic.ini` | Configuração do Alembic |
| `README.md` | Apresentação do projeto e guia de uso |

#### Docker (`docker/`)

| Arquivo | Função |
|---|---|
| `docker-compose.yml` | Sobe PostgreSQL 16 com healthcheck, SCRAM auth, hardening CIS |
| `postgres/init.sql` | Cria extensões `uuid-ossp` e `citext` no boot do banco |

#### Documentação (`docs/`)

| Arquivo | Função |
|---|---|
| `ESCOPO_CONGELADO.md` | Contrato do que entra e do que não entra na v1.0 |
| `BRD.md` | Business Requirements Document |
| `SRS.md` | Software Requirements Specification (IEEE 830) |
| `ARCHITECTURE.md` | Documento arquitetural detalhado |
| `SECURITY_THREAT_MODEL.md` | STRIDE + OWASP + NIST + log SCA |
| `EVIDENCIAS.md` | Documento de evidências para o professor |
| `PROJETO_COMPLETO.md` | Este documento mestre |
| `REPO_STRUCTURE.md` | Árvore canônica e bootstrap |
| `diagrams/use_case.puml` | Diagrama de casos de uso |
| `diagrams/er.puml` | Entidade-Relacionamento |
| `diagrams/class.puml` | Classes nas 4 camadas |
| `diagrams/sequence_ingestion.puml` | Sequência da ingestão |
| `diagrams/sequence_query.puml` | Sequência da query |
| `diagrams/security_dfd.puml` | DFD com trust boundaries |

#### Código-fonte (`src/docuvector/`)

```
src/docuvector/
├── __init__.py                              # Expõe __version__
├── main.py                                  # create_app() + lifespan + CORS
│
├── config/
│   ├── __init__.py
│   └── settings.py                          # Pydantic Settings + validators
│
├── domain/                                  # CAMADA 1
│   ├── entities/                            # User, Document, Chunk, QueryRecord
│   ├── interfaces/                          # 10 interfaces (contratos)
│   └── exceptions.py                        # Erros de domínio tipados
│
├── application/                             # CAMADA 2
│   ├── auth_use_case.py
│   ├── document_crud_use_case.py
│   ├── ingestion_use_case.py
│   ├── retrieval_use_case.py
│   ├── answer_use_case.py
│   ├── compression_benchmark_use_case.py    # ★ diferencial
│   ├── embedding_benchmark_use_case.py      # ★ diferencial
│   └── metrics_use_case.py
│
├── infrastructure/                          # CAMADA 3
│   ├── persistence/
│   │   ├── database.py                      # engine + session factory
│   │   ├── models.py                        # ORM SQLAlchemy
│   │   └── *_repository_impl.py
│   ├── vector/chroma_vector_store.py
│   ├── embeddings/
│   │   ├── openai_provider.py
│   │   └── sentence_transformers_provider.py
│   ├── compression/                         # ★ diferencial
│   │   ├── pca_compressor.py
│   │   ├── random_projection_compressor.py
│   │   ├── int8_compressor.py
│   │   └── binary_compressor.py
│   ├── extraction/
│   │   ├── pypdf_extractor.py
│   │   ├── txt_extractor.py
│   │   └── md_extractor.py
│   ├── splitting/recursive_splitter.py
│   ├── security/
│   │   ├── bcrypt_hasher.py
│   │   └── jwt_service.py
│   └── logging/structlog_config.py
│
├── api/                                     # CAMADA 4
│   ├── deps.py                              # DI providers
│   ├── middleware/
│   │   ├── auth.py
│   │   ├── audit.py
│   │   └── rate_limit.py
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── document.py
│   │   ├── query.py
│   │   └── benchmark.py
│   └── routers/
│       ├── health.py
│       ├── auth.py
│       ├── documents.py
│       ├── queries.py
│       ├── benchmarks.py
│       └── metrics.py
│
└── web/                                     # CAMADA 4 (frontend SSR)
    ├── routes.py                            # rotas HTML
    ├── static/css/custom.css
    └── templates/
        ├── base.html                        # layout jurídico
        ├── login.html
        ├── dashboard.html
        ├── documents.html
        ├── ask.html                         # chat jurídico
        ├── benchmarks.html                  # ★ tela do diferencial
        ├── metrics.html
        ├── audit.html
        └── partials/                        # componentes HTMX
```

### 6.3 Como as pastas se conversam

Diagrama textual do fluxo de dependência:

```
api/routers/*  ──┐
                 ├──► application/*_use_case.py  ──► domain/interfaces/*  (abstrações)
web/routes.py ──┘                                       │
                                                        │ implementadas por
                                                        ▼
                                              infrastructure/**/*_impl.py
                                                        │
                                                        │ usa
                                                        ▼
                                          (SQLAlchemy, Chroma, OpenAI, ...)
```

**Regra prática:** Quando você quer adicionar uma feature, comece pelo `domain/interfaces/` (defina o contrato), depois `application/` (orquestre), depois `infrastructure/` (implemente), por último `api/` (exponha em HTTP).

### 6.4 Scripts (`scripts/`)

| Arquivo | Função |
|---|---|
| `seed_users.py` | Cria admin + user1 + user2 a partir de `.env`. Idempotente. |

### 6.5 Testes (`tests/`)

Organização espelha a estrutura de produção:

```
tests/
├── conftest.py                       # fixtures compartilhadas
├── unit/                             # testes unitários puros
│   ├── domain/test_entities.py
│   ├── application/test_*_use_case.py
│   └── infrastructure/
│       ├── test_pca_compressor.py
│       ├── test_random_projection_compressor.py
│       ├── test_int8_compressor.py
│       ├── test_recursive_splitter.py
│       └── test_bcrypt_hasher.py
└── integration/                      # testes com banco + Chroma
    ├── test_health.py
    ├── test_auth_flow.py
    ├── test_document_crud.py
    ├── test_authorization.py         # BOLA
    └── test_benchmark_endpoint.py
```

---

## 7. Fluxos do sistema (passo a passo)

### 7.1 Fluxo de ingestão de documento

```
1. Usuário faz upload de PDF jurídico via tela /documents
2. Front HTMX envia POST multipart para /api/v1/documents
3. AuthMiddleware valida JWT
4. DocumentsRouter valida tamanho ≤ 10 MB e formato
5. Router chama IngestionUseCase.execute(user, file, provider, compression)
6. Use case cria registro Document com status=pending
7. PyPdfExtractor extrai texto cru do PDF
   ├─ Se PDF sem texto: marca failed, audit failure, retorna 422
   └─ Se PDF válido: continua
8. RecursiveSplitter divide em chunks de 1000 chars com overlap 200
9. EmbeddingProvider (OpenAI ou E5) gera embeddings
   ├─ E5 aplica prefixo "passage: " internamente
   └─ OpenAI envia raw via API
10. (Opcional) Compressor faz fit + transform nos embeddings
    └─ Calcula ratio, retention, RAM, tempos
11. ChromaVectorStore.upsert(chunks, vectors, metadata={owner_id, doc_id, provider, method})
12. DocumentRepository.update(status=indexed, dimensões, métricas)
13. AuditRepository.append(action=document_uploaded, success)
14. Router retorna HTTP 201 com payload
15. Front HTMX atualiza tabela de documentos sem reload
```

### 7.2 Fluxo de consulta (pergunta ao documento)

```
1. Usuário digita pergunta jurídica + seleciona contrato + provider
2. Front envia POST para /api/v1/queries
3. AuthMiddleware valida JWT
4. QueriesRouter chama AnswerUseCase.execute(user, question, doc_id, provider)
5. DocumentRepository.find_by_id(doc_id)
6. Verifica autorização (owner_id == user.id) OU (user.role == admin)
   ├─ Se não autorizado: audit forbidden, retorna 404 (mascara existência)
   └─ Se autorizado: continua
7. RetrievalUseCase é chamado
   a. EmbeddingProvider.embed_query(question) cronometrado
   b. ChromaVectorStore.search(vector, top_k=5, filters={doc_id, owner_id})
   c. Filtra resultados por score ≥ 0.6
8. Se nenhum chunk passou do threshold:
   └─ Retorna "não encontrei informação suficiente" sem chamar LLM
9. Se há chunks:
   a. Monta prompt template (sistema = juridicamente neutro; user = contexto + pergunta)
   b. LLM (gpt-4o-mini) gera resposta, cronometrado
   c. Persiste QueryRecord com tempos e fontes
10. Router retorna resposta + fontes (chunk_id, score, snippet) + tempos
11. Front renderiza no chat panel jurídico
```

### 7.3 Fluxo do benchmark de compressão (DIFERENCIAL)

```
1. Usuário acessa /benchmarks e seleciona documento
2. Front envia POST para /api/v1/documents/{id}/benchmark-compression
3. CompressionBenchmarkUseCase.execute(user, document_id)
4. Verifica ownership
5. Lê vetores originais do documento no ChromaDB
6. Para cada um dos 4 compressores:
   a. compressor.fit(vetores)
   b. cronometra fit_time_ms
   c. compressor.transform(vetores)
   d. cronometra transform_time_ms
   e. Calcula:
      - original_dim, compressed_dim
      - ram_bytes_original (vetores.nbytes)
      - ram_bytes_compressed (resultado.nbytes)
      - compression_ratio_bytes
      - semantic_retention: amostra N=50 pares aleatórios,
        calcula cosine(orig_a, orig_b) e cosine(comp_a, comp_b),
        retorna pearsonr entre as duas séries
   f. Persiste CompressionResult no banco
7. Router retorna tabela JSON dos 4 resultados
8. Front renderiza:
   ├─ Tabela comparativa
   └─ Gráfico de barras SVG com ratio vs retention
```

### 7.4 Fluxo do benchmark de embedders (DIFERENCIAL)

```
1. Usuário insere pergunta em /benchmarks → aba "Embedders"
2. Front envia POST para /api/v1/queries/benchmark-embedders
3. EmbeddingBenchmarkUseCase.execute(question, document_id)
4. Para cada provider {openai, e5_local}:
   a. cronometra embed_query
   b. cronometra search em ChromaDB
   c. estima custo (tokens × USD/1M tokens, zero para local)
5. Router retorna comparação:
   {
     "openai": {"embed_ms": 320, "search_ms": 12, "cost_usd": 0.00002},
     "local":  {"embed_ms": 85,  "search_ms": 11, "cost_usd": 0.0}
   }
6. Front exibe lado a lado, com tempo cronometrado em destaque
```

---

## 8. Modelo de dados

### 8.1 Banco relacional (PostgreSQL)

Cinco tabelas. Detalhes em `docs/diagrams/er.puml`.

| Tabela | Função | Cardinalidade |
|---|---|---|
| `users` | Autenticação e roles (admin, user) | 1 user → N documents |
| `documents` | Metadados de documentos + estado de indexação | 1 document → N chunks (em Chroma) |
| `queries` | Histórico de perguntas com respostas e tempos | N queries → 1 document |
| `compression_benchmarks` | Resultados dos 4 compressores por documento | 4 benchmarks → 1 document |
| `audit_logs` | Auditoria de ações sensíveis | N events → 0..1 user |

### 8.2 Vector store (ChromaDB)

Uma coleção `documents`. Cada item representa um chunk com:

```python
{
  "id": "chunk_uuid",
  "embedding": [0.123, -0.456, ...],     # vetor float32 ou int8 ou bytes
  "document": "texto do chunk",           # opcional, para debug
  "metadata": {
    "document_id": "...",
    "owner_id": "...",                    # ESSENCIAL para multi-tenant
    "chunk_index": 3,
    "embedding_provider": "openai",
    "compression_method": "none"
  }
}
```

**Decisão de design:** todo `search()` no Chroma inclui filtro de metadata por `owner_id` (e por `document_id` quando aplicável). Isso garante isolamento multi-tenant na camada vetorial, não apenas na relacional.

### 8.3 Decisão: por que dois bancos?

Postgres é fortíssimo em queries relacionais, transacionais, com integridade referencial. Não é eficiente para busca por similaridade em milhões de vetores. ChromaDB é otimizado para HNSW (Hierarchical Navigable Small World), o algoritmo padrão de ANN (Approximate Nearest Neighbor).

Alternativa considerada: `pgvector` (extensão Postgres). Descartada porque adiciona dependência específica do schema do Postgres e complica a separação clara entre relacional (metadados) e vetorial (busca semântica). Em arquitetura Clean, manter os dois separados deixa cada peça com responsabilidade única.

---

## 9. Segurança e DevSecOps em profundidade

Detalhes completos em `docs/SECURITY_THREAT_MODEL.md`. Resumo conceitual aqui.

### 9.1 Filosofia: Defense in Depth + Shift-Left

**Defense in Depth:** Múltiplas camadas de defesa. Se uma falha, outra contém. Exemplos:
- Senha: bcrypt cost 12 + rate limit + mensagem genérica em erro.
- Acesso indevido a documento: filtro por owner_id no SQL + filtro por owner_id no Chroma + retorno 404 + audit log forbidden.

**Shift-Left:** Os controles de segurança rodam o mais cedo possível no ciclo de desenvolvimento. Cada commit local passa pelos hooks; cada push roda o CI. Bugs de segurança detectados antes do PR são mais baratos que detectados em produção.

### 9.2 Pirâmide de testes de segurança aplicada

```
                            ┌─────────────────────┐
                            │ Threat Model (doc)  │  ← STRIDE + OWASP + NIST
                            └──────────┬──────────┘
                                       │ informa
                         ┌─────────────┴─────────────┐
                         │  Testes de autorização    │  ← BOLA test, mass assignment test
                         │  (integration)            │
                         └─────────────┬─────────────┘
                                       │ valida
                       ┌───────────────┴───────────────┐
                       │  SAST + SCA + Secrets + SBOM  │  ← automatizado, CI + pre-commit
                       └───────────────┬───────────────┘
                                       │ apoia
                  ┌────────────────────┴────────────────────┐
                  │   Tipagem estrita (mypy) + Lint (ruff)  │  ← previne classes inteiras de bugs
                  └─────────────────────────────────────────┘
```

### 9.3 Catálogo de práticas DevSecOps aplicadas

| Prática | Ferramenta | Onde roda | O que detecta |
|---|---|---|---|
| **SAST** (Static Application Security Testing) | Bandit | pre-commit + CI | Padrões inseguros em Python (eval, exec, hardcoded passwords, weak crypto) |
| **SCA** (Software Composition Analysis) | pip-audit (OSV.dev) | CI + `just sca` | CVEs em dependências diretas e transitivas |
| **Secret scanning** | detect-secrets, detect-private-key | pre-commit | API keys, tokens, chaves privadas comitadas |
| **SBOM** (Software Bill of Materials) | cyclonedx-py | CI | Inventário completo de dependências para rastreabilidade |
| **Tipagem estática** | mypy strict + plugin Pydantic | pre-commit + CI | Bugs estruturais antes do runtime |
| **Lint de segurança** | ruff (regras S = flake8-bandit, B = bugbear) | pre-commit + CI | Anti-padrões em Python |
| **Validação de input** | Pydantic v2 com `model_config` restritivo | runtime em todo endpoint | Tipos errados, mass assignment, payload malicioso |
| **Rate limiting** | SlowAPI | runtime no `/auth/login` | Brute force de senha |
| **Hash de senha** | bcrypt cost 12 | runtime em registro/login | Reverter hash via brute force |
| **Auth token assinado** | JWT HS256 com segredo ≥ 32 bytes | runtime | Forjamento de identidade |
| **Audit logging** | structlog + tabela `audit_logs` | runtime | Repúdio de ação, rastreabilidade |
| **Container hardening** | docker-compose com `no-new-privileges`, `cap_drop: ALL` | container | Escape de container |
| **Princípio do menor privilégio (CI)** | `permissions: contents: read` no workflow | CI | Workflow malicioso reescrevendo main |
| **Pinning de dependências** | uv.lock | sempre | Supply chain via versão maliciosa surpresa |
| **Threat model documentado** | Markdown em `docs/` | revisão manual | Lacunas conceituais |

### 9.4 Mapeamento OWASP API Top 10 (2023)

| OWASP API | Mitigação no DocuVector Lite | Coberto |
|---|---|---|
| API1: BOLA | Filtro `owner_id` em SQL e Chroma; HTTP 404 ao invasor; audit forbidden | ✓ |
| API2: Broken Auth | bcrypt 12 + JWT + rate limit + erro genérico | ✓ |
| API3: Broken Property Level Auth | Schemas Pydantic não expõem `role`, `owner_id`, `status` | ✓ |
| API4: Unrestricted Resource Consumption | Upload ≤ 10 MB; rate limit; modelo LLM barato | ✓ |
| API5: Broken Function Level Auth | Dependency `require_admin` em rotas administrativas | ✓ |
| API6: Sensitive Business Flow | Não aplicável (sem fluxos de pagamento) | N/A |
| API7: SSRF | Aplicação não fetcha URLs do usuário | N/A |
| API8: Security Misconfiguration | Postgres SCRAM, CORS restrito, settings com validators | ✓ |
| API9: Improper Inventory | SBOM CycloneDX, API versionada `/api/v1/` | ✓ |
| API10: Unsafe API Consumption | Resposta OpenAI tratada como string opaca, nunca interpretada | ✓ |

### 9.5 Mapeamento NIST SSDF (SP 800-218)

| Prática SSDF | Implementação |
|---|---|
| PS.1 Proteger o código | Git + pre-commit barrando código não conforme |
| PS.2 Verificar integridade | SBOM CycloneDX gerada e arquivada no CI |
| PW.4 Reusar software seguro | Stack open source bem mantida, sem criptografia caseira |
| PW.5 Código aderente a práticas seguras | ruff (regras S), bandit |
| PW.6 Build e segredos seguros | `.env` fora do Git, detect-secrets no pre-commit |
| PW.7 Revisão de código | Pre-commit + CI com SAST e mypy strict |
| PW.8 Teste de vulnerabilidades | Testes de autorização (BOLA) automatizados |
| PW.9 Configuração segura por default | `.env.example` com valores seguros, CORS restrito |
| RV.1 Identificação contínua | pip-audit no CI a cada push |
| RV.2 Resposta a vulnerabilidades | Política: CVE CRITICAL bloqueia merge; HIGH gera issue. Log SCA em `SECURITY_THREAT_MODEL.md` seção 13 |

---

## 10. Pipeline CI/CD completo

### 10.1 Diagrama de pipeline

```
┌──────────────────────────────────────────────────────────┐
│   DESENVOLVEDOR (local, Windows)                         │
│                                                          │
│   git commit                                             │
│        │                                                 │
│        ▼                                                 │
│   ┌────────────────────────────────────────┐             │
│   │  PRE-COMMIT HOOKS (.pre-commit-...)    │             │
│   │  - check-ast, check-yaml, check-toml   │             │
│   │  - ruff (lint + format)                │             │
│   │  - mypy strict                         │             │
│   │  - bandit (SAST)                       │             │
│   │  - detect-secrets                      │             │
│   │  - detect-private-key                  │             │
│   │  - end-of-file-fixer, trailing-ws      │             │
│   │  - check-added-large-files (>2MB)      │             │
│   └────────────────────────────────────────┘             │
│        │                                                 │
│        │ commit aceito                                   │
│        ▼                                                 │
│   git push                                               │
└────────│─────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│   GITHUB ACTIONS (.github/workflows/ci.yml)                │
│                                                            │
│   1. Checkout                                              │
│   2. Instalar uv (cache automático)                        │
│   3. Configurar Python 3.11                                │
│   4. uv sync --extra dev --frozen                          │
│                                                            │
│   5. Lint            ruff check src tests                  │
│   6. Format check    ruff format --check src tests         │
│   7. Type check      mypy src tests                        │
│   8. SAST            bandit -c pyproject.toml -r src       │
│   9. SCA             pip-audit (com allowlist)             │
│   10. Secrets        detect-secrets scan --baseline ...    │
│   11. SBOM           cyclonedx-py environment -o sbom.json │
│   12. Smoke test     pytest tests/integration/test_health  │
│   13. Upload artifacts                                     │
│        ├─ sbom.json                                        │
│        ├─ bandit-report.json                               │
│        └─ pip-audit-report.json                            │
└────────────────────────────────────────────────────────────┘
```

### 10.2 Gates obrigatórios

Nada vai para `main` se algum gate falhar. Isso é configurável em GitHub branch protection rules (Sprint 8).

| Gate | Critério |
|---|---|
| Lint | ruff sem erros |
| Format | ruff format check sem diff |
| Type | mypy strict sem erros |
| SAST | Bandit sem HIGH/CRITICAL |
| SCA | pip-audit sem CVE CRITICAL não-allowlisted |
| Secrets | detect-secrets sem novos segredos |
| Tests | pytest 100% green com coverage ≥ 70% (a partir Sprint 6) |
| SBOM | Gera sem erro |

### 10.3 Reprodutibilidade local

O `justfile` espelha exatamente o que o CI roda. Comando único:

```bash
just ci
```

Permite ao desenvolvedor reproduzir o CI inteiro antes do push. Isso é prática sênior: o CI nunca deve te surpreender.

---

## 11. Plano por sprint (8 sprints, 14 dias)

### Sprint 1 — Fundação documental e técnica (Dias 1-3) ✅ CONCLUÍDA

**Objetivo:** Sair do dia 14 sem dívida de fundação.

**Entregáveis concluídos:**
- BRD, SRS, escopo congelado
- 6 diagramas PlantUML
- Threat model formal
- pyproject.toml, justfile, pre-commit, .env.example
- Docker Compose com Postgres healthy
- GitHub Actions CI com 6 gates
- Skeleton FastAPI com /health e Swagger
- Smoke test integration

**Definition of Done:** ✓ todos os arquivos no Git, CI verde, app sobe local.

### Sprint 2 — Autenticação e CRUD de documentos (Dias 4-5)

**Objetivo:** Atender ao núcleo funcional do edital.

**Dia 4 — Auth:**
- Entidades de domínio: `User`, `UserRole`, `TokenPayload`
- Interfaces: `UserRepository`, `PasswordHasher`, `TokenService`, `AuditRepository`
- Modelos ORM SQLAlchemy
- Alembic init + migration inicial
- `BcryptPasswordHasher`, `JwtTokenService`
- `AuthUseCase` (login, me)
- Router `/api/v1/auth`
- Middleware `AuthMiddleware`
- `scripts/seed_users.py` (idempotente, 3 usuários)
- Testes integration de auth flow

**Dia 5 — CRUD documentos:**
- Entidade `Document`, enums `FileFormat`, `DocumentStatus`
- `DocumentRepository` (interface + impl)
- `DocumentCrudUseCase`
- Router `/api/v1/documents` (5 endpoints CRUD)
- Audit log de ações
- Testes integration de CRUD + autorização (BOLA)

**Definition of Done:** Pessoa loga, faz CRUD, user1 não vê doc de user2, admin vê tudo.

### Sprint 3 — Pipeline RAG (Dias 6-7)

**Objetivo:** Fazer o sistema "entender" os documentos.

**Dia 6 — Ingestão:**
- Interface `EmbeddingProvider`, `DocumentExtractor`, `TextSplitter`, `VectorStore`
- `PyPdfExtractor`, `TxtExtractor`, `MdExtractor`
- `RecursiveSplitter` (1000/200, alinhado a RGN-06)
- `SentenceTransformersEmbeddingProvider` (com prefixos E5)
- `OpenAIEmbeddingProvider`
- `ChromaVectorStore`
- `IngestionUseCase` completo
- Endpoint POST `/api/v1/documents` com upload multipart

**Dia 7 — Retrieval e resposta:**
- `RetrievalUseCase`
- `AnswerUseCase`
- LLM client (OpenAI gpt-4o-mini)
- Prompt template jurídico
- Router `/api/v1/queries`
- Testes integration de query

**Definition of Done:** Upload de contrato, pergunta sobre cláusula, resposta com fontes em ≤ 3 segundos.

Sim, totalmente possível. Inclusive alinha perfeitamente com o diferencial declarado da Sprint 4 (compressão observável). É exatamente o tipo de feature que diferencia um TCC nota alta de um nota média.
O que dá para mostrar (todos viáveis)
MétricaDe onde vemCusto de implementarLatência por provider (ms p50/p95)audit_logs.metadata.latency_ms (já gravado no Bloco 5/AnswerUseCase)Trivial: query SQL agregadaTokens consumidos / custo USD acumuladoaudit_logs.metadata.tokens_used + cost_usdTrivial: SUM no SQLTamanho vetor original vs comprimidodocuments.original_dimension e documents.compressed_dimension (já têm coluna na migration 0001!)Trivial: cálculo no frontBytes em disco antes/depoisoriginal_dim × 4 bytes × n_chunks vs compressed_dim × 4 bytes × n_chunksTrivial: aritméticaEstimativa em R$ no Pinecone/Qdrant CloudTabela fixa de preços × bytes economizadosTrivial: tabela hardcoded no frontRetenção semântica (qualidade)documents.semantic_retention (já tem coluna!)Médio: precisa benchmark da Sprint 4
Por que é eficiente

Você JÁ tem os campos no schema. Olha models.py: compression_method, original_dimension, compressed_dimension, semantic_retention, ingest_time_ms estão lá nullable, esperando a Sprint 4 preencher.
Audit log JÁ grava o que precisa. O IngestionUseCase (Bloco 3) registra embedding_provider, embedding_dimensions, chunks_created. O AnswerUseCase (Bloco 4) vai gravar latency_ms e cost_usd. Você só agrega.
Cálculo de R$ economizado é aritmética simples. Não exige ML, não exige análise estatística complexa. Tabela de preços × delta de bytes.
Audiência adora. Banca jurídica/acadêmica entende "economia em reais" muito melhor que "redução de dimensionalidade via PCA".

O que adicionar no roadmap (proposta)
Sprint 4 (★ diferencial) — adiciona:

Endpoint GET /api/v1/metrics/dashboard que agrega tudo
Templates do dashboard em Jinja2 (já planejado para Sprint 5, mas a aba de métricas vira parte da Sprint 4)

Sprint 5 (frontend Jinja2) — adiciona:

Aba "Indicadores" no menu
Cards visuais: latência média, custo acumulado, bytes economizados, R$ projetados
Comparativo OpenAI vs E5 lado a lado (gráfico de barras simples com HTMX + CSS, sem Chart.js)

Trabalho extra estimado

2-3h para o endpoint de métricas (Sprint 4)
3-4h para a aba na UX (Sprint 5)
Total: ~6h distribuídos em 2 sprints já planejadas

Frase para a banca

"O sistema mede o próprio funcionamento. A aba Indicadores mostra latência por provedor, custo acumulado em USD, e — o ponto pedagógico mais relevante — a economia em reais que a compressão de embeddings traz se o sistema for migrado para Pinecone ou Qdrant Cloud. O aluno que usa o sistema vê o impacto financeiro de uma decisão técnica, não só lê sobre ele."

Recomendação: anoto isso como Bloco 5 da Sprint 4 (depois dos 4 compressores e benchmarks que já estavam planejados). Quer que eu adicione formalmente ao roadmap no documento AVALIACAO_ESTADO_VS_PLANO.md?

### Sprint 4 — Compressão e benchmarks (Dias 8-9) ★ DIFERENCIAL

**Dia 8 — Compressores:**
- Interface `Compressor`
- `PcaCompressor`, `RandomProjectionCompressor`, `Int8Compressor`, `BinaryCompressor`
- `CompressionBenchmarkUseCase` com cálculo de:
  - Dimensões, ratio em bytes, RAM, tempos
  - Retenção semântica via Pearson
- Endpoint `POST /api/v1/documents/{id}/benchmark-compression`
- Testes unit dos 4 compressores (property-based com hypothesis)

**Dia 9 — Benchmark de embedders:**
- `EmbeddingBenchmarkUseCase`
- Estimativa de custo OpenAI (tokens × preço)
- Endpoint `POST /api/v1/queries/benchmark-embedders`
- Reindexação com troca de compressor (`POST /api/v1/documents/{id}/reindex`)

**Definition of Done:** Tabela com 4 compressores comparados + tabela com 2 embedders.

### Sprint 5 — Frontend jurídico Jinja2 + HTMX (Dias 10-11)

**Dia 10 — Estrutura visual:**
- `base.html` com sidebar jurídica
- Login (`/login`)
- Dashboard com cards de métricas
- Documentos com upload HTMX

**Dia 11 — Telas de valor:**
- Chat jurídico (`/ask`)
- Benchmarks (`/benchmarks`) com tabela + gráfico SVG
- Métricas (`/metrics`)
- Auditoria (`/audit`)

**Definition of Done:** Visitante consegue navegar sem documentação.

### Sprint 6 — Testes automatizados robustos (Dia 12)

**Objetivo:** Cobertura ≥ 70%, mais que os 5 mínimos exigidos pelo edital.

15 testes pelo menos:
- 4 unit dos compressores (property-based)
- 1 unit do splitter
- 3 unit dos use cases (com mocks)
- 4 integration de auth e CRUD
- 1 integration de query
- 1 integration de benchmark
- 1 integration de autorização (BOLA)

**Definition of Done:** `pytest --cov` mostra ≥ 70%.

### Sprint 7 — Polish DevSecOps e observabilidade (Dia 13)

- structlog em todos os use cases
- Tratamento global de exceções no FastAPI
- Página de erro 404, 401, 403, 500 amigável
- Rate limit no `/auth/login`
- Branch protection rules no GitHub
- Re-revisão do threat model
- Validação manual de OWASP API Top 10

**Definition of Done:** Sistema não quebra silenciosamente; CI verde; threat model atualizado.

### Sprint 8 — Documentação final e ensaio (Dia 14)

**Manhã:**
- README.md final
- EVIDENCIAS.md com prints organizados
- PDF dos diagramas
- Tag de release `v1.0.0`

**Tarde:**
- Ensaio cronometrado da apresentação 10 min (3 vezes)
- Gravação de vídeo backup
- Push final

**Definition of Done:** Pronto para defesa.

---

## 12. Checklist de implementação por sprint

> Use este checklist como guia de execução. Marque [✓] quando concluído.

### Sprint 1 ✅
- [✓] `docs/ESCOPO_CONGELADO.md`
- [✓] `docs/BRD.md`
- [✓] `docs/SRS.md`
- [✓] `docs/SECURITY_THREAT_MODEL.md`
- [✓] 6 diagramas PlantUML
- [✓] `pyproject.toml`
- [✓] `.pre-commit-config.yaml`
- [✓] `docker/docker-compose.yml`
- [✓] `docker/postgres/init.sql`
- [✓] `.env.example`
- [✓] `.gitignore`
- [✓] `.pip-audit.toml`
- [✓] `justfile`
- [✓] `.github/workflows/ci.yml`
- [✓] `src/docuvector/__init__.py`
- [✓] `src/docuvector/main.py`
- [✓] `src/docuvector/config/settings.py`
- [✓] `src/docuvector/infrastructure/logging/structlog_config.py`
- [✓] `src/docuvector/api/routers/health.py`
- [✓] `tests/conftest.py`
- [✓] `tests/integration/test_health.py`
- [✓] CI verde
- [✓] App sobe localmente

### Sprint 2 (próxima)
- [ ] `src/docuvector/domain/entities/user.py`
- [ ] `src/docuvector/domain/entities/document.py`
- [ ] `src/docuvector/domain/entities/audit_event.py`
- [ ] `src/docuvector/domain/interfaces/user_repository.py`
- [ ] `src/docuvector/domain/interfaces/document_repository.py`
- [ ] `src/docuvector/domain/interfaces/audit_repository.py`
- [ ] `src/docuvector/domain/interfaces/password_hasher.py`
- [ ] `src/docuvector/domain/interfaces/token_service.py`
- [ ] `src/docuvector/domain/exceptions.py`
- [ ] `src/docuvector/infrastructure/persistence/database.py`
- [ ] `src/docuvector/infrastructure/persistence/models.py`
- [ ] `src/docuvector/infrastructure/persistence/user_repository_impl.py`
- [ ] `src/docuvector/infrastructure/persistence/document_repository_impl.py`
- [ ] `src/docuvector/infrastructure/persistence/audit_repository_impl.py`
- [ ] `src/docuvector/infrastructure/security/bcrypt_hasher.py`
- [ ] `src/docuvector/infrastructure/security/jwt_service.py`
- [ ] `src/docuvector/application/auth_use_case.py`
- [ ] `src/docuvector/application/document_crud_use_case.py`
- [ ] `src/docuvector/api/schemas/auth.py`
- [ ] `src/docuvector/api/schemas/document.py`
- [ ] `src/docuvector/api/middleware/auth.py`
- [ ] `src/docuvector/api/middleware/audit.py`
- [ ] `src/docuvector/api/routers/auth.py`
- [ ] `src/docuvector/api/routers/documents.py`
- [ ] `src/docuvector/api/deps.py`
- [ ] `alembic.ini`
- [ ] `migrations/env.py`
- [ ] `migrations/versions/0001_initial.py`
- [ ] `scripts/seed_users.py`
- [ ] `tests/integration/test_auth_flow.py`
- [ ] `tests/integration/test_document_crud.py`
- [ ] `tests/integration/test_authorization.py`

### Sprint 3
- [ ] Interfaces de embeddings, extração, splitter, vector store
- [ ] 3 extractors (PDF, TXT, MD)
- [ ] RecursiveSplitter
- [ ] 2 EmbeddingProviders (OpenAI e E5)
- [ ] ChromaVectorStore
- [ ] IngestionUseCase, RetrievalUseCase, AnswerUseCase
- [ ] LLM client
- [ ] Routers /documents (POST upload), /queries (POST query)
- [ ] Testes de query

### Sprint 4 ★ DIFERENCIAL
- [ ] Interface Compressor
- [ ] PcaCompressor com testes unit
- [ ] RandomProjectionCompressor com testes unit
- [ ] Int8Compressor com testes unit
- [ ] BinaryCompressor com testes unit
- [ ] CompressionBenchmarkUseCase
- [ ] EmbeddingBenchmarkUseCase
- [ ] Endpoints de benchmark
- [ ] Reindex endpoint

### Sprint 5 (Frontend Jurídico)
- [ ] Template base.html com identidade jurídica
- [ ] Login com copy jurídico
- [ ] Dashboard com cards
- [ ] Documentos com upload HTMX
- [ ] Chat jurídico com fontes citadas
- [ ] Benchmarks com tabela + gráfico
- [ ] Métricas
- [ ] Auditoria

### Sprint 6 (Testes)
- [ ] Cobertura ≥ 70% verificada no CI

### Sprint 7 (DevSecOps polish)
- [ ] Tratamento global de exceções
- [ ] Páginas de erro
- [ ] Rate limit no login
- [ ] Branch protection rules
- [ ] Threat model revisado

### Sprint 8 (Documentação)
- [ ] README final
- [ ] EVIDENCIAS.md com prints
- [ ] Apresentação ensaiada
- [ ] Vídeo backup
- [ ] Tag v1.0.0

---

## 13. Estratégia de testes

### 13.1 Pirâmide

```
                     ┌────────────────────┐
                     │  E2E (apresentação)│   1 cenário ao vivo
                     └────────────────────┘
                   ┌──────────────────────────┐
                   │   Integration (≥ 8)      │   banco, Chroma, HTTP
                   └──────────────────────────┘
                 ┌──────────────────────────────┐
                 │    Unit (≥ 8)                │   sem I/O, com mocks
                 └──────────────────────────────┘
```

### 13.2 Testes obrigatórios (15+)

**Unit:**
1. `test_pca_compressor_preserves_variance_above_threshold` (hypothesis: array sintético, PCA deve preservar > 80% da variância com 64 componentes)
2. `test_random_projection_preserves_distances_jl_lemma` (hypothesis: JL com tolerância)
3. `test_int8_compressor_round_trip_within_tolerance` (quantização não deve perder mais de 5% no cosine)
4. `test_binary_compressor_outputs_correct_dimension` (bits = float32 dims / 32)
5. `test_recursive_splitter_respects_chunk_size`
6. `test_bcrypt_hasher_verifies_correctly_and_rejects_wrong`
7. `test_jwt_service_round_trip_and_rejects_tampered`
8. `test_settings_validates_chunk_overlap_less_than_chunk_size`

**Integration:**
9. `test_health_endpoint_returns_ok_payload`
10. `test_user_can_login_and_access_me`
11. `test_unauthenticated_request_returns_401`
12. `test_user_can_upload_and_list_own_documents`
13. `test_user_cannot_access_other_user_document_returns_404`
14. `test_admin_can_access_any_document`
15. `test_query_returns_answer_with_sources`
16. `test_benchmark_compression_returns_four_methods`

### 13.3 Hypothesis para compressores (property-based)

Testes property-based geram automaticamente centenas de casos. Exemplo conceitual:

```
Para qualquer array sintético de embeddings (N entre 50 e 500, dim entre 100 e 1000):
  Após PCA(64):
    - dimensão de saída é exatamente 64
    - retenção de variância > 0.6 (mais frouxo que produção, prova robustez)
    - sem NaN nem Inf no resultado
```

---

## 14. Roteiro de apresentação (10 minutos)

> **Audiência:** professor super exigente, banca. **Tom:** sério, denso, mas com momentos de impacto visual.

| Tempo | Cena | Mensagem-chave |
|---|---|---|
| 0:00–0:30 | Abertura | Problema: documentos jurídicos viram conhecimento caro. Solução: portal RAG com custos visíveis. |
| 0:30–1:00 | Login | Segurança visível: bcrypt 12, JWT, audit. |
| 1:00–2:00 | Upload de contrato | Pipeline em tempo real: extract → chunk → embed → persist. |
| 2:00–4:30 | **Benchmark de compressão** | 4 métodos lado a lado, métricas reais sobre o documento da banca. Trade-off explicado. |
| 4:30–6:30 | **Benchmark de embedders** | Mesma pergunta, OpenAI vs local, cronômetro vivo. Custo vs latência vs privacidade. |
| 6:30–7:30 | Chat jurídico | Pergunta sobre cláusula, resposta com fontes citadas (chunk + score). |
| 7:30–8:30 | Admin + auditoria | Troca de conta, mostra audit log com status=forbidden de tentativa de acesso. |
| 8:30–9:30 | Engenharia | CI verde, Swagger, testes, SBOM, threat model, .pip-audit.toml com decisão registrada. |
| 9:30–10:00 | Fechamento | "Atendi ao edital, entreguei diferencial, segui Clean Architecture, apliquei DevSecOps real. Aqui está o threat model com 38 ameaças catalogadas." |

### 14.1 Frases de defesa pré-prontas

> "Optei por **não usar LangChain** porque o framework abstrai exatamente o que eu queria demonstrar. Implementei o pipeline em código próprio, auditável e tipado."

> "Apliquei **Clean Architecture de Robert C. Martin** com quatro camadas. Posso trocar Chroma por Qdrant, FastAPI por Litestar, Postgres por MySQL: o domínio não muda uma linha."

> "Em DevSecOps, fui além de testes. Implementei SAST com Bandit, SCA com pip-audit, SBOM em CycloneDX e threat model formal com STRIDE cruzado com OWASP API Top 10 e NIST SSDF."

> "O pip-audit identificou o advisory MAL-2026-4750 sobre FastAPI. Sem detalhe público em bases oficiais, classifiquei como **risco residual aceito**, isolei o FastAPI em grupo opcional de dependências, documentei a decisão em `.pip-audit.toml` e marquei revisão obrigatória na Sprint 8. Mostra processo de decisão, não fuga."

---

## 15. Glossário técnico

| Termo | Definição |
|---|---|
| **RAG** | Retrieval-Augmented Generation. Combina recuperação de trechos + geração via LLM. |
| **Embedding** | Vetor numérico de alta dimensão que representa o significado semântico de um texto. |
| **Chunk** | Trecho de texto resultado da segmentação de um documento original. |
| **Cosine similarity** | Métrica de similaridade entre dois vetores. Vale 1 (idênticos) a -1 (opostos). |
| **PCA** | Principal Component Analysis. Projeção linear que preserva variância. |
| **Random Projection** | Projeção aleatória baseada no Lemma de Johnson-Lindenstrauss. |
| **Quantização Int8** | Mapear float32 para inteiros de 8 bits. Reduz 4x a RAM. |
| **Quantização Binária** | Mapear float32 para 1 bit (sinal). Reduz 32x a RAM. |
| **Retenção semântica** | Métrica que quantifica quanto a similaridade entre pares é preservada após compressão. |
| **HNSW** | Hierarchical Navigable Small World. Algoritmo padrão de ANN. |
| **ANN** | Approximate Nearest Neighbor. Busca por vizinhos próximos sem garantia exata. |
| **JWT** | JSON Web Token. Padrão de token assinado para autenticação. |
| **bcrypt** | Algoritmo de hash de senha com salt e cost factor configurável. |
| **OWASP API Top 10** | Top 10 das vulnerabilidades em APIs, mantido pela OWASP Foundation. |
| **STRIDE** | Spoofing, Tampering, Repudiation, Info Disclosure, DoS, Elevation. Metodologia da Microsoft. |
| **NIST SSDF** | Secure Software Development Framework. Padrão americano de governo. |
| **SAST** | Static Application Security Testing. Análise de código fonte. |
| **SCA** | Software Composition Analysis. Análise de dependências. |
| **SBOM** | Software Bill of Materials. Inventário formal de dependências. |
| **BOLA** | Broken Object Level Authorization. Falha clássica em APIs. |
| **mass assignment** | Vulnerabilidade onde input do usuário sobrescreve campos sensíveis. |
| **CycloneDX** | Padrão de formato de SBOM mantido pela OWASP. |
| **trust boundary** | Fronteira no DFD onde nível de confiança muda. |
| **shift-left** | Mover controles de qualidade/segurança para mais cedo no ciclo. |
| **defense in depth** | Múltiplas camadas de defesa redundantes. |
| **Dependency Rule** | Regra do Clean Architecture: dependências apontam para dentro. |
| **DI (Dependency Injection)** | Injetar dependências via construtor em vez de instanciar internamente. |
| **idempotência** | Propriedade onde executar a operação N vezes tem o mesmo efeito que executar uma vez. |

---

## 16. FAQ defensivo (perguntas que a banca pode fazer)

### Sobre escolha de stack

**Q: Por que não usou .NET conforme preferência do edital?**
A: O ecossistema de embeddings e RAG é nativo em Python. Reimplementar em .NET adicionaria complexidade não relacionada ao escopo, exigiria chamadas a Python via subprocess ou conversão para ONNX. Compensei a divergência com qualidade técnica acima do baseline em outras dimensões (arquitetura, DevSecOps, threat model formal).

**Q: Por que não usou LangChain?**
A: LangChain abstrai exatamente o que eu queria demonstrar: extração, chunking, embedding, retrieval. Implementar manualmente prova compreensão do pipeline. Além disso, reduziu 90 dependências, simplifica auditoria de segurança e elimina superfície de breaking changes da major bump do LangChain 1.x.

**Q: Por que não usou React no front?**
A: React adiciona build npm, node_modules, bundle de 200+ KB. Jinja2 + HTMX entrega interatividade suficiente para o caso de uso com 15 KB de JavaScript, sem ferramentas adicionais. Para uma UI jurídica densa em informação, server-side é o padrão clássico e adequado.

### Sobre arquitetura

**Q: O que é Clean Architecture e por que você usou?**
A: Clean Architecture, formulada por Robert C. Martin, organiza código em camadas concêntricas com a regra de que dependências apontam apenas para dentro. Permite trocar peças externas (banco, framework web, vector store) sem reescrever lógica de negócio. Aplicada aqui em 4 camadas: domínio, aplicação, infraestrutura, apresentação.

**Q: Como você garante que a regra de dependência é respeitada?**
A: Domínio importa apenas Python stdlib e Pydantic. Aplicação importa domínio. Infraestrutura importa domínio e bibliotecas externas. Apresentação importa todas, mas não contém regra de negócio. Mypy strict captura violações de tipo. Code review captura violações estruturais.

**Q: Por que cada compressor tem sua própria classe?**
A: Single Responsibility Principle. Cada compressor tem uma única razão para mudar. Adicionar Product Quantization no futuro é criar uma nova classe implementando a interface `Compressor`, sem tocar nas existentes. Open/Closed Principle.

### Sobre segurança

**Q: O que faz um usuário não conseguir ver documentos de outro?**
A: Defense in depth em 4 camadas: (1) JWT no header valida identidade; (2) Repositório SQL filtra por `owner_id` em todo SELECT; (3) ChromaDB filtra por `owner_id` em todo search; (4) Resposta retorna 404, não 403, para não revelar existência. Teste automatizado `test_user_cannot_access_other_user_document` valida.

**Q: Como você lida com prompt injection no documento?**
A: Prompt template estrito instrui o LLM a responder apenas com base no contexto fornecido e ignorar instruções dentro do contexto. Contexto é delimitado por marcadores explícitos. Resposta é tratada como string opaca, nunca interpretada como código. Trade-off conhecido: nenhuma defesa contra prompt injection é perfeita (modelo de ameaça aceita esse risco residual).

**Q: O pip-audit detectou MAL-2026-4750. Como você lidou?**
A: Pesquisei em OSV, GHSA, NVD: nenhum detalhe público disponível. Classifiquei como **risco residual aceito** com 4 mitigações compensatórias: (1) FastAPI isolado em grupo opcional; (2) execução apenas localhost; (3) revisão obrigatória na Sprint 8; (4) allowlist documentada em `.pip-audit.toml`. Postura DevSecOps real não é "zero alertas", é rastreabilidade e decisão consciente.

### Sobre o diferencial técnico

**Q: Qual o cálculo da retenção semântica?**
A: Amostra N=50 pares aleatórios de chunks. Para cada par calcula `cosine(embedding_original_A, embedding_original_B)` e `cosine(embedding_comprimido_A, embedding_comprimido_B)`. Retorna o coeficiente de correlação de Pearson entre as duas séries. Valor 1.0 = preservação perfeita; 0.0 = embeddings comprimidos não preservam estrutura original. Métrica defensável academicamente.

**Q: Por que justamente esses 4 compressores?**
A: Cobrem o espectro do trade-off. PCA: linear, determinística, exige fit. Random Projection: aleatória, sem fit, baseada em teorema clássico (JL). Int8: mantém dimensão, reduz 4x RAM. Binary: mantém dimensão, reduz 32x RAM, perda visível. Permite mostrar didaticamente que "comprimir" não é uma decisão, são múltiplas decisões com semânticas diferentes.

**Q: Por que dois embedders?**
A: Para tornar visível o trade-off custo vs latência vs privacidade. OpenAI: melhor qualidade média, custa USD, manda dados para terceiros. E5 local: gratuito após download, roda 100% offline, qualidade comparável em PT-BR. Em um sistema jurídico real, esse trade-off é decisão de compliance, não de engenharia.

### Sobre processo

**Q: Como você decidiu o que entra e o que não entra no escopo?**
A: Sprint 0 (preparação) gerou `ESCOPO_CONGELADO.md` com 21 itens dentro e 20 itens fora. Cada item tem justificativa. Mudanças após o congelamento exigem adendo registrado no próprio documento. Disciplina de escopo é decisão arquitetural, não burocracia.

**Q: O que aconteceria se a OpenAI ficasse fora do ar durante a apresentação?**
A: Sistema continua 100% funcional com embedder local E5 e LLM Ollama (configurável). Tela do benchmark mostra OpenAI como indisponível, mas demonstração não trava. Risco RIS-01 e RIS-02 estão no BRD com mitigação documentada.

**Q: Como você sabe que o sistema é testável?**
A: Cada use case recebe dependências via construtor. Em teste, injeto mocks (InMemoryUserRepository, FakeEmbeddingProvider, etc) e exercito a lógica sem subir banco. Em integração, uso fixtures Pytest com Postgres real em container. Cobertura ≥ 70% como gate de merge.

---

## 17. Referências bibliográficas

### Livros
- **Martin, Robert C.** Clean Code: A Handbook of Agile Software Craftsmanship. Prentice Hall, 2008.
- **Martin, Robert C.** Clean Architecture: A Craftsman's Guide to Software Structure and Design. Prentice Hall, 2017.
- **Fowler, Martin.** Patterns of Enterprise Application Architecture. Addison-Wesley, 2002.
- **Newman, Sam.** Building Microservices, 2nd ed. O'Reilly, 2021. (referência conceitual, não usamos microsserviços)

### Padrões e frameworks de segurança
- **OWASP API Security Top 10** (2023). https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- **NIST SP 800-218** Secure Software Development Framework. https://csrc.nist.gov/publications/detail/sp/800-218/final
- **Microsoft STRIDE**: documentação interna de threat modeling.
- **CIS Docker Benchmark** para hardening de containers.

### Tecnologias
- **FastAPI**: https://fastapi.tiangolo.com/
- **Pydantic v2**: https://docs.pydantic.dev/
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/
- **ChromaDB**: https://docs.trychroma.com/
- **Sentence Transformers**: https://sbert.net/
- **OpenAI Embeddings**: https://platform.openai.com/docs/guides/embeddings
- **HTMX**: https://htmx.org/

### Papers acadêmicos relevantes
- **Johnson, W. B.; Lindenstrauss, J.** "Extensions of Lipschitz mappings into a Hilbert space." Contemporary Mathematics, 1984. (base teórica do Random Projection)
- **Wang, L. et al.** "Multilingual E5 Text Embeddings." Microsoft, 2024. (base do modelo `intfloat/multilingual-e5-small`)
- **Reimers, N.; Gurevych, I.** "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks." EMNLP, 2019. (base do sentence-transformers)
- **Karpukhin, V. et al.** "Dense Passage Retrieval for Open-Domain Question Answering." EMNLP, 2020. (base teórica do RAG)

### Edital e contexto acadêmico
- Edital do trabalho final da disciplina de Desenvolvimento de Sistemas, CEUB, semestre vigente.
- IEEE 830-1998: Recommended Practice for Software Requirements Specifications (adaptado para PT-BR no SRS).

---

## Como usar este documento

**Para desenvolvimento:** Use a seção 12 (checklist) como guia diário.

**Para defesa:** Memorize as seções 3 (decisões), 5 (arquitetura), 9 (segurança), 14 (roteiro), 16 (FAQ).

**Para slides:** Use as seções 2 (diferencial), 5 (camadas), 7 (fluxos), 9 (DevSecOps), 14 (roteiro). Cada uma vira 2-3 slides.

**Para o documento de evidências do professor:** Combine este documento com os prints da seção 11 do `SECURITY_THREAT_MODEL.md`.

---

**Fim do documento mestre.**
