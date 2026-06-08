# SRS — Software Requirements Specification

**Projeto:** JurisVector
**Versão:** 1.0
**Data:** 25/05/2026
**Autor:** Davi Rosa F. e Breno Manoel
**Documento de origem:** `docs/BRD.md` v1.0
**Padrão de referência:** IEEE 830 (adaptado, em PT-BR)

---

## 1. Introdução

### 1.1 Propósito

Este documento especifica formalmente os requisitos funcionais e não funcionais do JurisVector v1.0. É o contrato técnico que orienta a implementação, os testes e a avaliação do trabalho final da disciplina de Desenvolvimento de Sistemas.

### 1.2 Escopo do produto

O escopo desta especificação é coextensivo ao documento `docs/ESCOPO_CONGELADO.md` v1.0. Qualquer divergência aponta para erro a ser corrigido neste SRS.

### 1.3 Definições, acrônimos e abreviações

| Termo | Significado |
|---|---|
| RF | Requisito Funcional |
| RNF | Requisito Não Funcional |
| RGN | Regra de Negócio (definida no BRD) |
| UC | Caso de Uso |
| RBAC | Role-Based Access Control |
| BOLA | Broken Object Level Authorization |
| JWT | JSON Web Token |
| TLS | Transport Layer Security |
| p95 | 95º percentil |

### 1.4 Referências

1. BRD do projeto (`docs/BRD.md` v1.0).
2. Edital da disciplina de Desenvolvimento de Sistemas.
3. OWASP API Security Top 10 (2023).
4. NIST SP 800-218 (SSDF).
5. Clean Architecture, Robert C. Martin (2017).

---

## 2. Descrição geral

### 2.1 Perspectiva do produto

JurisVector é uma aplicação web monolítica modular, com backend FastAPI e front-end server-side (Jinja2 + HTMX), persistência relacional em PostgreSQL via SQLAlchemy, e store vetorial em ChromaDB persistente local. Não depende de serviços de nuvem para funcionar; depende opcionalmente da API OpenAI quando o usuário escolhe o provedor remoto.

### 2.2 Funções principais

1. Autenticação e autorização baseada em token JWT com papéis (admin, user).
2. CRUD de documentos com upload, listagem, leitura, atualização e exclusão.
3. Pipeline de ingestão: extração, chunking, embedding, opcional compressão, persistência.
4. Consulta semântica com retorno de resposta e fontes.
5. Benchmark de algoritmos de compressão (PCA, Random Projection, Int8, Binary).
6. Benchmark de provedores de embedding (OpenAI vs Sentence Transformers).
7. Painel administrativo com métricas e auditoria.

### 2.3 Características dos usuários

| Característica | Admin | User |
|---|---|---|
| Login | sim | sim |
| Upload de documentos | sim | sim |
| Visualizar próprios documentos | sim | sim |
| Visualizar documentos de outros | sim | não |
| Excluir próprios documentos | sim | sim |
| Excluir documentos de outros | sim | não |
| Acessar painel de métricas globais | sim | não |
| Acessar log de auditoria | sim | não |

### 2.4 Restrições gerais

1. A aplicação roda em Python 3.11.
2. O banco PostgreSQL é executado em container Docker.
3. O sistema deve operar em rede local sem dependência de internet, salvo quando o usuário escolhe explicitamente o provedor OpenAI.
4. Não há HTTPS terminado pela aplicação; terminação TLS seria responsabilidade de proxy reverso fora do escopo.

### 2.5 Premissas e dependências

1. Docker Desktop disponível no Windows do avaliador.
2. Python 3.11 e `uv` instalados localmente.
3. Acesso à internet pública no momento da apresentação não é obrigatório.
4. Chave OpenAI disponível em variável de ambiente apenas se o usuário desejar testar o provedor remoto.

---

## 3. Requisitos funcionais

Cada requisito é numerado, possui prioridade (M = obrigatório, S = should, C = could) e referencia BRD/caso de uso quando aplicável.

### 3.1 Autenticação e gestão de sessão

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-001 | O sistema deve permitir login por e-mail e senha, retornando token JWT válido em caso de sucesso | M | RN-01, UC-01 |
| RF-002 | O sistema deve rejeitar credenciais inválidas com mensagem genérica que não revele se o e-mail existe | M | OWASP API2 |
| RF-003 | O sistema deve aplicar rate limit no endpoint de login (10 tentativas por minuto por IP) | M | RGN, mitigação brute force |
| RF-004 | O sistema deve permitir logout, invalidando o token no front (remoção do storage) | M | UC-02 |
| RF-005 | O sistema deve expor endpoint `/me` que retorna dados do usuário autenticado | M | UC-03 |
| RF-006 | O sistema deve recusar qualquer requisição protegida sem token válido com HTTP 401 | M | OWASP API2 |
| RF-007 | Token JWT deve ter expiração configurável (default 60 minutos) | M | RGN-03 |

### 3.2 Gestão de usuários

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-010 | Usuários iniciais (1 admin + 2 users) devem ser seedados via script `scripts/seed_users.py` lendo de `.env` | M | Decisão arquitetural |
| RF-011 | Senhas devem ser armazenadas exclusivamente como hash bcrypt | M | RN-02, OWASP A02:2021 |
| RF-012 | Script de seed deve ser idempotente: nova execução não duplica usuários | M | DevOps |
| RF-013 | Endpoint `/auth/register` existe apenas para admin (v1.0 sem registro público) | S | Escopo |

### 3.3 Gestão de documentos (CRUD completo)

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-020 | Usuário autenticado deve poder fazer upload de documento (PDF, TXT, MD) | M | RN-05, UC-04 |
| RF-021 | Upload deve rejeitar arquivos acima de 10 MB com HTTP 413 | M | RGN-04 |
| RF-022 | Upload deve rejeitar formatos não suportados com HTTP 415 e mensagem clara | M | RN-06 |
| RF-023 | Upload deve rejeitar PDF sem texto extraível com HTTP 422 e mensagem clara | M | RGN-05 |
| RF-024 | Usuário deve poder listar seus próprios documentos com paginação | M | RN-03, UC-05 |
| RF-025 | Admin deve poder listar todos os documentos com filtro opcional por owner | M | RN-04 |
| RF-026 | Usuário deve poder visualizar detalhes de um documento próprio | M | UC-06 |
| RF-027 | Usuário comum tentando acessar documento de outro usuário deve receber HTTP 404 (cliente) e gerar evento `status=forbidden` no audit log | M | RGN-10, OWASP API1 |
| RF-028 | Usuário deve poder atualizar metadados do próprio documento (nome, tags) | M | UC-07 |
| RF-029 | Usuário deve poder excluir documento próprio; exclusão remove embeddings em ChromaDB | M | RGN-13, UC-08 |
| RF-030 | Usuário deve poder solicitar reindexação com troca de embedder ou de método de compressão | M | UC-09 |

### 3.4 Pipeline de ingestão

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-040 | O sistema deve extrair texto de PDF usando `pypdf` | M | Escopo |
| RF-041 | O sistema deve extrair texto de TXT e MD diretamente | M | Escopo |
| RF-042 | O sistema deve segmentar texto em chunks com tamanho alvo de 1000 caracteres e overlap de 200 | M | RGN-06 |
| RF-043 | O sistema deve gerar embeddings de cada chunk usando o provedor escolhido pelo usuário | M | RN-07 |
| RF-044 | O sistema deve persistir embeddings em ChromaDB com metadata vinculada ao documento | M | Escopo |
| RF-045 | O sistema deve persistir metadados do documento em PostgreSQL (filename, owner, status, provider, dimensão, ratio, retenção) | M | Escopo |
| RF-046 | O status do documento deve transitar entre `pending`, `indexed`, `failed` | M | UX |
| RF-047 | Falha em qualquer etapa da ingestão marca o documento como `failed` e registra a causa no audit log | M | Robustez |

### 3.5 Embedders intercambiáveis

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-050 | O sistema deve oferecer provedor OpenAI (`text-embedding-3-small`) configurável via `.env` | M | RN-09 |
| RF-051 | O sistema deve oferecer provedor local Sentence Transformers (`intfloat/multilingual-e5-small`, 384 dimensões, multilíngue com suporte forte a PT-BR) | M | RN-09 |
| RF-052 | O usuário deve poder selecionar o provedor no momento do upload | M | RN-09 |
| RF-053 | O usuário deve poder selecionar o provedor no momento da query | M | RN-09 |
| RF-054 | A query deve ser embedada com o mesmo provedor usado na ingestão do documento, salvo seleção explícita | M | Consistência semântica |
| RF-055 | O sistema deve retornar o tempo de embedding (ms) e o custo estimado em USD para cada chamada | M | OBJ-03 |

### 3.6 Compressão de embeddings

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-060 | O sistema deve oferecer compressor PCA com dimensão configurável | M | RN-10 |
| RF-061 | O sistema deve oferecer compressor Random Projection com dimensão configurável | M | RN-10 |
| RF-062 | O sistema deve oferecer compressor Int8 (quantização min-max por dimensão) | M | RN-10 |
| RF-063 | O sistema deve oferecer compressor Binary (sign quantization, 1 bit por dimensão) | M | RN-10 |
| RF-064 | O sistema deve calcular para cada compressor: dimensão original, dimensão comprimida, ratio em bytes, RAM original, RAM comprimida, tempo de fit, tempo de transform | M | OBJ-02 |
| RF-065 | O sistema deve calcular retenção semântica via correlação de Pearson entre similaridades cosine antes e depois da compressão, com N=50 pares amostrais | M | OBJ-02 |
| RF-066 | O endpoint `/documents/{id}/benchmark-compression` deve retornar os 4 métodos avaliados sobre os embeddings do documento | M | OBJ-02 |
| RF-067 | A tabela de benchmark deve ser visualizável no front com gráfico comparativo | M | Demo |

### 3.7 Consulta semântica

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-070 | O usuário deve poder enviar pergunta em linguagem natural associada a um documento | M | RN-08, UC-10 |
| RF-071 | O sistema deve recuperar top-k=5 chunks com score acima de 0.6 (cosine), threshold configurável por query | M | RGN-07, RGN-08 |
| RF-072 | O sistema deve gerar resposta via LLM (OpenAI `gpt-4o-mini`) com contexto dos chunks | M | RN-08 |
| RF-073 | A resposta deve incluir as fontes citadas (chunk_id, score, trecho) | M | UX |
| RF-074 | Quando nenhum chunk passar do threshold, o sistema deve responder "não encontrei informação suficiente" sem chamar o LLM | M | Custo + honestidade |
| RF-075 | O endpoint `/queries/benchmark-embedders` deve executar a mesma pergunta nos dois provedores e retornar tempo + custo de cada um | M | OBJ-03 |

### 3.8 Auditoria e métricas

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-080 | O sistema deve registrar evento de auditoria para: login bem-sucedido, login falho, upload, exclusão de documento, acesso negado | M | RN-11 |
| RF-081 | Cada evento de auditoria deve conter: user_id (quando aplicável), action, resource_type, resource_id, status, IP, timestamp, metadata JSON | M | NIST SSDF |
| RF-082 | Admin deve poder listar logs de auditoria com paginação | M | RN-11 |
| RF-083 | Admin deve poder visualizar métricas agregadas: total de documentos, total de queries, ratio médio de compressão, retenção média, tempo médio de resposta | M | UX admin |

### 3.9 API e documentação

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-090 | A API deve ser documentada via Swagger UI em `/docs` | M | RN-12 |
| RF-091 | Toda rota deve possuir summary, description e schemas de request e response | M | RN-12 |
| RF-092 | A API deve seguir convenções REST (verbos HTTP, status codes apropriados) | M | Boa prática |
| RF-093 | A API deve versionar prefixo (`/api/v1/`) | M | Evolução |

### 3.10 Front-end

| ID | Descrição | Prioridade | Origem |
|---|---|---|---|
| RF-100 | O front deve oferecer tela de login | M | Edital |
| RF-101 | O front deve oferecer dashboard com cards de métricas | M | Demo |
| RF-102 | O front deve oferecer tela de documentos com upload e tabela | M | Demo |
| RF-103 | O front deve oferecer tela de chat para consulta com fontes | M | Demo |
| RF-104 | O front deve oferecer tela de benchmark de compressão com tabela e gráfico | M | OBJ-02 |
| RF-105 | O front deve oferecer tela de benchmark de embedders | M | OBJ-03 |
| RF-106 | O front deve oferecer tela de auditoria (apenas admin) | M | RN-11 |
| RF-107 | O front deve permitir trocar embedder e método de compressão sem reload (HTMX) | S | UX |

---

## 4. Requisitos não funcionais

### 4.1 Segurança (RNF-SEG)

| ID | Descrição | Medida |
|---|---|---|
| RNF-SEG-01 | Senhas armazenadas com bcrypt, cost 12 | Inspeção do banco |
| RNF-SEG-02 | Tokens JWT assinados com segredo de mínimo 256 bits | `len(JWT_SECRET) >= 32` |
| RNF-SEG-03 | Variáveis de ambiente sensíveis em `.env`, jamais commitadas | `.gitignore` + `detect-secrets` |
| RNF-SEG-04 | Endpoint protegido sem token retorna 401 | Teste automatizado |
| RNF-SEG-05 | Acesso a recurso de outro usuário retorna 404 (cliente) com `status=forbidden` no log | Teste automatizado + RGN-10 |
| RNF-SEG-06 | Mass assignment bloqueado via Pydantic com `model_config` restritivo | Code review |
| RNF-SEG-07 | Rate limit no login: 10 tentativas/minuto/IP | Teste manual |
| RNF-SEG-08 | Análise SAST por Bandit no CI, sem findings HIGH | `bandit -r src` |
| RNF-SEG-09 | Análise SCA por pip-audit, sem CVE CRITICAL | `pip-audit` |
| RNF-SEG-10 | Detecção de segredos por detect-secrets no pre-commit | Hook ativo |
| RNF-SEG-11 | SBOM CycloneDX gerada e arquivada no CI | Artefato do workflow |
| RNF-SEG-12 | Conformidade básica com OWASP API Top 10 (2023) cobertura: API1, API2, API3, API5, API8 | Checklist no evidências |

### 4.2 Desempenho (RNF-DES)

| ID | Descrição | Meta |
|---|---|---|
| RNF-DES-01 | Tempo de resposta de query end-to-end com embedder local | < 3s (p95) |
| RNF-DES-02 | Tempo de ingestão de PDF de 5 páginas com embedder local | < 15s |
| RNF-DES-03 | Tempo de subida do stack (`docker compose up` + app) | < 60s |
| RNF-DES-04 | Tamanho máximo de documento | 10 MB |
| RNF-DES-05 | Concorrência mínima suportada na demo | 3 usuários simultâneos |

### 4.3 Usabilidade (RNF-USA)

| ID | Descrição |
|---|---|
| RNF-USA-01 | Toda mensagem de erro ao usuário é em PT-BR e descreve a ação corretiva |
| RNF-USA-02 | Layout consistente com sidebar fixa, header com identidade do usuário e área principal |
| RNF-USA-03 | Feedback visual durante operações longas (loader/indicador HTMX) |
| RNF-USA-04 | Tabelas paginadas com ordenação clara |

### 4.4 Manutenibilidade (RNF-MAN)

| ID | Descrição | Medida |
|---|---|---|
| RNF-MAN-01 | Código segue Clean Architecture com 4 camadas (domain, application, infrastructure, api) | Estrutura de pastas |
| RNF-MAN-02 | Dependência aponta sempre para dentro (Dependency Rule) | Code review |
| RNF-MAN-03 | Lint `ruff check` sem erro | CI |
| RNF-MAN-04 | Tipagem `mypy --strict` sem erro | CI |
| RNF-MAN-05 | Funções com complexidade ciclomática ≤ 10 | `ruff` regra C901 |
| RNF-MAN-06 | Cobertura de testes ≥ 70% em `domain` e `application` | `pytest --cov` |
| RNF-MAN-07 | Naming semântico (variáveis e funções revelam intenção, sem abreviações obscuras) | Code review |
| RNF-MAN-08 | Pre-commit hooks barram problemas antes do commit | Hook ativo |

### 4.5 Observabilidade (RNF-OBS)

| ID | Descrição |
|---|---|
| RNF-OBS-01 | Logs estruturados em JSON via structlog |
| RNF-OBS-02 | Cada requisição HTTP gera linha de log com correlation_id, user_id (se autenticado), método, path, status, duração |
| RNF-OBS-03 | Erros não tratados são logados com stack trace completo |
| RNF-OBS-04 | Audit log persistido em tabela dedicada (não apenas em arquivo) |
| RNF-OBS-05 | Endpoint `/health` retorna status do app e do banco |

### 4.6 Portabilidade (RNF-POR)

| ID | Descrição |
|---|---|
| RNF-POR-01 | Aplicação roda em Windows, macOS e Linux com Python 3.11 |
| RNF-POR-02 | Banco PostgreSQL via Docker Compose, sem instalação nativa |
| RNF-POR-03 | Caminhos de arquivo usam `pathlib.Path` (sem `/` ou `\` hardcoded) |

### 4.7 Conformidade (RNF-CON)

| ID | Descrição |
|---|---|
| RNF-CON-01 | Atendimento integral ao edital da disciplina |
| RNF-CON-02 | Documentação seguindo IEEE 830 adaptado |
| RNF-CON-03 | Diagramas em PlantUML versionados no repositório |

---

## 5. Interfaces externas

### 5.1 Interface de usuário (web)

Front-end server-side renderizado com Jinja2 sobre FastAPI. HTMX para interações sem reload. Tailwind CSS via CDN. Sem build npm. Telas listadas em RF-100 a RF-106.

### 5.2 API REST

Prefixo `/api/v1/`. Autenticação via header `Authorization: Bearer <token>` exceto em `/api/v1/auth/login`. Documentação OpenAPI em `/docs`.

### 5.3 Banco de dados relacional

PostgreSQL 16 em container Docker. Conexão via SQLAlchemy 2.0 com `psycopg[binary]`. Schema versionado via Alembic.

### 5.4 Store vetorial

ChromaDB em modo persistente local (`PersistentClient`). Persistência em volume nomeado no Docker Compose, ou diretório local em desenvolvimento.

### 5.5 Provedor de embedding remoto

OpenAI Embeddings API (`text-embedding-3-small`, 1536 dimensões). Autenticação por API key em `.env`.

### 5.6 Provedor de embedding local

Modelo Sentence Transformers `intfloat/multilingual-e5-small` (384 dimensões), baixado automaticamente na primeira execução (~470 MB de pesos).

**Restrição operacional do modelo E5:** o modelo exige prefixos textuais para diferenciar consultas de passagens indexadas:

- Chunks de documento devem ser embedados com o prefixo `"passage: "` antes do texto.
- Perguntas de usuário devem ser embedadas com o prefixo `"query: "` antes do texto.

Esse detalhe é encapsulado dentro do `SentenceTransformersEmbeddingProvider` e não vaza para a camada de aplicação. Quando o provider OpenAI é usado, os prefixos não são aplicados (não fazem parte da especificação do `text-embedding-3-small`).

### 5.7 Provedor de LLM

OpenAI Chat Completions (`gpt-4o-mini`). Autenticação por API key em `.env`. Opcionalmente, configuração para Ollama local fica como evolução futura.

---

## 6. Restrições de design

1. Camadas seguem regra de dependência da Clean Architecture: domínio puro, aplicação depende apenas de domínio, infraestrutura implementa interfaces de domínio, apresentação compõe com aplicação.
2. Domínio não importa FastAPI, SQLAlchemy ou ChromaDB.
3. Use cases recebem dependências via construtor (DI explícito), nunca via singleton global.
4. Cada compressor implementa interface única (`Compressor`) com `fit`, `transform`, `metadata`.
5. Cada provedor de embedding implementa interface única (`EmbeddingProvider`) com `embed_texts`, `dimension`, `name`, `cost_per_million_tokens`.
6. Comentários em código somente para explicar regra de negócio não óbvia, restrição externa, ou trade-off de segurança/desempenho.
7. Nomes semânticos obrigatórios. Proibido `df`, `data`, `obj`, `tmp` como identificadores.

---

## 7. Matriz de rastreabilidade

Liga BRD → SRS → Caso de Uso → Endpoint/Tela.

| Requisito de negócio (BRD) | Requisito funcional (SRS) | Caso de uso | Endpoint(s) | Tela(s) |
|---|---|---|---|---|
| RN-01 | RF-001, RF-006 | UC-01 | `POST /auth/login` | `/login` |
| RN-02 | RNF-SEG-01, RF-011 | UC-01 | `POST /auth/login` | n/a |
| RN-03 | RF-024, RF-027 | UC-05 | `GET /documents` | `/documents` |
| RN-04 | RF-025, RF-082, RF-083 | UC-11 | `GET /documents`, `/audit-logs`, `/metrics/summary` | `/audit`, `/metrics` |
| RN-05 | RF-020 a RF-030 | UC-04 a UC-09 | `POST/GET/PATCH/DELETE /documents` | `/documents` |
| RN-06 | RF-022 | UC-04 | `POST /documents` | `/documents` |
| RN-07 | RF-043, RF-044 | UC-04 | `POST /documents` | n/a |
| RN-08 | RF-070, RF-072, RF-073 | UC-10 | `POST /queries` | `/ask` |
| RN-09 | RF-050 a RF-055, RF-075 | UC-10, UC-12 | `POST /queries`, `POST /queries/benchmark-embedders` | `/ask`, `/benchmarks` |
| RN-10 | RF-060 a RF-067 | UC-13 | `POST /documents/{id}/benchmark-compression` | `/benchmarks` |
| RN-11 | RF-080 a RF-082 | UC-14 | `GET /audit-logs` | `/audit` |
| RN-12 | RF-090 a RF-093 | n/a | `/docs` | n/a |
| RN-13 | Infraestrutura | n/a | n/a | n/a |
| RN-14 | RNF-MAN-01 | n/a | n/a | n/a |
| RN-15 | RNF-MAN-06 | n/a | n/a | n/a |
| RN-16 | RNF-OBS-03, RF-022, RF-023 | n/a | tratamento global | n/a |
| RN-17 | RNF-MAN-01 a RNF-MAN-08 | n/a | n/a | n/a |

---

## 8. Apêndices

### Apêndice A — Status HTTP padronizados

| Cenário | Código |
|---|---|
| Sucesso em GET, PATCH | 200 |
| Sucesso em POST com criação | 201 |
| Sucesso sem corpo | 204 |
| Requisição malformada | 400 |
| Não autenticado | 401 |
| Autorizado, mas proibido (somente quando faz sentido revelar a existência) | 403 |
| Recurso não encontrado ou acesso indevido a recurso de outro user | 404 |
| Payload muito grande | 413 |
| Tipo não suportado | 415 |
| Validação de regra de negócio falhou | 422 |
| Rate limit | 429 |
| Erro inesperado | 500 |

### Apêndice B — Schema de evento de auditoria

```json
{
  "id": "uuid",
  "user_id": "uuid|null",
  "action": "login|login_failed|document_uploaded|document_deleted|access_denied|query_executed",
  "resource_type": "user|document|query",
  "resource_id": "uuid|null",
  "status": "success|failure|forbidden",
  "ip_address": "string",
  "metadata": { "...": "..." },
  "created_at": "iso8601"
}
```

### Apêndice C — Convenção de mensagens de erro ao cliente

```json
{
  "error": {
    "code": "string_machine_readable",
    "message": "Mensagem em PT-BR clara e acionável",
    "details": { "...": "..." }
  }
}
```
