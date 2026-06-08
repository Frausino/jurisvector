# JurisVector

**RAG Jurídico com compressão observável de embeddings**

[![CI](https://github.com/Frausino/docuvector-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/Frausino/docuvector-lite/actions)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Coverage](https://img.shields.io/badge/coverage-86%25-green)

JurisVector é um portal web que faz o pipeline RAG funcionar de ponta a ponta (upload, indexação, consulta, resposta com fontes) e expõe o custo de compressão de embeddings de forma observável. O usuário pode escolher entre 5 espaços vetoriais diferentes para cada consulta e comparar a qualidade do retrieval com métricas IR padrão (Recall@K, Precision@K, MRR).

---

## Funcionalidades principais

- Upload e indexação de documentos jurídicos (PDF, TXT)
- Consulta por linguagem natural com RAG (Ollama local ou OpenAI)
- 5 coleções ChromaDB em paralelo: original, Int8, Binary, PCA, Random Projection
- Comparação A/B de respostas entre duas coleções
- Métricas IR (Recall@K, MRR) por coleção
- Dashboard operacional: latência, custo, retenção semântica, economia de bytes
- Autenticação multi-tenant com JWT + RBAC
- Compressão sob demanda por documento com persistência

---

## Pré-requisitos

- Python 3.12
- PostgreSQL 16 (ou Docker)
- Ollama com `qwen2.5:7b` instalado
- `uv` para gestão de pacotes
- `just` como task runner

---

## Instalação

```bash
# 1. Clonar
git clone https://github.com/Frausino/docuvector-lite.git
cd docuvector-lite

# 2. Configurar ambiente
cp docs/.env.example .env
# Editar .env com suas credenciais

# 3. Instalar dependências
uv sync --extra api --extra dev

# 4. Subir PostgreSQL
docker compose up -d

# 5. Rodar migrations
just migrate

# 6. Iniciar aplicação
just dev
# Admin criado automaticamente no primeiro startup
```

Acesse `http://127.0.0.1:8000/app/chat`.

---

## Comandos principais

```bash
just ci          # lint + type check + bandit + test + coverage
just dev         # servidor com hot-reload
just migrate     # alembic upgrade head
just test        # pytest com coverage
just lint        # ruff check
just type        # mypy
just seed-admin  # cria admin manualmente (alternativa ao startup automático)
```

---

## Estrutura de documentação

```
docs/
├── README.md                   # este arquivo
├── BRD.md                      # Business Requirements Document
├── SRS.md                      # Software Requirements Specification
├── ESCOPO_CONGELADO.md         # escopo v1.0 congelado
├── ARCHITECTURE.md             # arquitetura técnica e decisões de design
├── SPRINTS.md                  # histórico de sprints e entregáveis
├── CHANGELOG.md                # histórico de versões
├── METHODOLOGY.md              # metodologia experimental (TCC)
├── SECURITY_THREAT_MODEL.md    # modelo de ameaças STRIDE + OWASP
├── .env.example                # variáveis de ambiente documentadas
└── diagrams/
    ├── class.puml              # diagrama de classes
    ├── er.puml                 # diagrama entidade-relacionamento
    ├── use_case.puml           # diagrama de casos de uso
    ├── sequence_ingestion.puml # fluxo de ingestão
    ├── sequence_query.puml     # fluxo de consulta
    └── security_dfd.puml       # data flow diagram de segurança
```

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI 0.115 + Python 3.12 |
| ORM | SQLAlchemy 2.0 |
| Banco | PostgreSQL 16 |
| Vector store | ChromaDB (local) |
| Embedding local | E5-small (HuggingFace) |
| LLM local | Ollama qwen2.5:7b |
| Frontend | Jinja2 + HTMX + Tailwind CDN |
| Auth | JWT + bcrypt |
| CI/CD | GitHub Actions |

---

## Documentação técnica

- Arquitetura detalhada: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Metodologia experimental: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)
- Segurança: [`docs/SECURITY_THREAT_MODEL.md`](docs/SECURITY_THREAT_MODEL.md)
- Histórico de sprints: [`docs/SPRINTS.md`](docs/SPRINTS.md)
