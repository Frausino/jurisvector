# Sprint 3 — Bloco 3: Embeddings + Vector Store + Ingestion

Pacote que entrega o coração do pipeline RAG: dois provedores de
embedding (OpenAI e E5 local), ChromaDB com filtro `owner_id` em
todas as operações, e o `IngestionUseCase` que orquestra
extract → split → embed → store com transições atômicas de status.

UX terá **escolha de provider** por upload (decisão arquitetural #2).
O `DocumentChunk` grava qual provider foi usado, habilitando o
benchmark de compressão da Sprint 4.

## Estrutura

```
sprint3-bloco3/
├── src/docuvector/
│   ├── application/
│   │   └── ingestion_use_case.py                              [NOVO]
│   ├── api/
│   │   ├── deps.py                                            [SUBSTITUI]
│   │   ├── routers/
│   │   │   └── documents.py                                   [SUBSTITUI]
│   │   └── schemas/
│   │       └── documents.py                                   [SUBSTITUI]
│   └── infrastructure/
│       ├── embeddings/
│       │   ├── __init__.py                                    [NOVO]
│       │   ├── factory.py                                     [NOVO]
│       │   ├── openai_embedder.py                             [NOVO]
│       │   └── sentence_transformers_embedder.py              [NOVO]
│       ├── extractors/
│       │   └── file_format_detector.py                        [NOVO]
│       └── vector_stores/
│           ├── __init__.py                                    [NOVO]
│           └── chroma_vector_store.py                         [NOVO]
└── tests/
    └── unit/
        ├── application/
        │   └── test_ingestion_use_case.py                     [NOVO]
        └── infrastructure/
            └── test_file_format_detector.py                   [NOVO]
```

## Pré-requisitos

- Bloco 1 (CRUD docs) já aplicado: este pacote SUBSTITUI o
  `routers/documents.py`, `schemas/documents.py` e `deps.py` daquele
  bloco, adicionando o endpoint POST e os providers.
- Bloco 2 (extractors + splitter) já aplicado.

## Como aplicar

```powershell
git checkout feature/sprint-3-rag-domain
Expand-Archive -Path .\sprint3-bloco3.zip -DestinationPath . -Force

git status                  # 13 arquivos (3 substituídos, 10 novos)

# Gates estáticos
just lint
just format-check
just type

# Testes unit (não precisam de banco nem Chroma real)
just test-unit
# esperado: 17 antigos + ~30 do Bloco 2 + ~20 do Bloco 3 verdes

# Sobe banco + Chroma (Chroma é embutido, não precisa de container)
just up
just migrate-status         # 0003_documents_and_chunks (head)

# Smoke manual no Swagger
just dev
# 1. POST /api/v1/auth/login → pega token
# 2. Authorize (cadeado) → cola token
# 3. GET /api/v1/documents/providers → ver lista de providers disponíveis
# 4. POST /api/v1/documents → upload PDF/TXT/MD escolhendo provider
# 5. GET /api/v1/documents → ver doc com status=embedded
```

## Decisões arquiteturais aplicadas

### 1. Escolha do provider por usuário (UX)
O usuário escolhe o `embedding_provider` no upload (form-data). Default
é `sentence_transformers` (E5 local, sem custo). OpenAI fica disponível
apenas se `OPENAI_API_KEY` estiver configurada (o endpoint
`/providers` filtra automaticamente). Isso permite à UX construir um
select dinâmico sem hardcoded.

### 2. Collections separadas por provider no Chroma
Vetores de OpenAI (1536d) e E5 (384d) têm dimensões incompatíveis e
não podem coexistir na mesma collection. Cada provider tem
`docuvector_openai` ou `docuvector_sentence_transformers`. O wrapper
`_DynamicVectorStore` em `deps.py` roteia transparentemente.

### 3. Prefixos E5 obrigatórios
`SentenceTransformersEmbedder` aplica `"query: "` em `embed_query` e
`"passage: "` em `embed_passages`. Sem isso o modelo degrada
severamente. A interface `EmbeddingProvider` força a distinção desde o
domínio.

### 4. Validação MIME por magic bytes
`file_format_detector.py` checa o conteúdo real (não confia no
`Content-Type` enviado). PDF detectado por `%PDF-`, TXT/MD por
heurística de texto + extensão. Sem dependência de `python-magic`
(que requer libmagic nativa).

### 5. Pipeline atômico com transições de status
`IngestionUseCase` move o `Document` por `UPLOADED → EXTRACTING →
EXTRACTED → CHUNKING → CHUNKED → EMBEDDING → EMBEDDED`. Falha em
qualquer etapa marca `FAILED` com `failure_reason`. O usuário sempre
vê o estado atual do upload.

### 6. Dedup por checksum SHA-256
Antes de processar, calcula `sha256(content)` e checa
`find_by_checksum_for_owner`. Hit no cache devolve o doc existente
com `was_already_ingested=True`. Evita custo de re-embedding e
duplicação no banco/Chroma.

### 7. Audit log com custo e telemetria
Sucesso de ingestão registra `chunks_created`, `embedding_provider`,
`embedding_model`, `embedding_dimensions`, `size_bytes` em
`audit_logs.metadata`. Habilita dashboard de custo futuro.

### 8. ChunkVector contém `document_filename` para citação
O VectorStore expõe esse campo no `RetrievedChunk` para que a UX possa
exibir "esta resposta veio do documento contrato_123.pdf". Sem precisar
de JOIN com `documents` na hora da pergunta.

### 9. Telemetria do Chroma desabilitada
`anonymized_telemetry=False` no `ChromaSettings`. Nada de phone-home
do Chroma para fora do sistema.

## Limitações conscientes

- **Sem retry customizado nos embedders.** O SDK OpenAI tem retry
  built-in (`max_retries=3`); para o E5 local não há motivo (operação
  local). Polish futuro pode adicionar circuit breaker se virar dor.
- **Token count por heurística (`len/4`).** Tiktoken adicionaria
  dependência pesada por benefício marginal. Polish: trocar quando
  o dashboard de custo precisar precisão exata.
- **Sem OCR para PDFs escaneados.** Documentos sem texto extraível
  vão para `FAILED` com motivo. Polish: adicionar Tesseract em sprint
  futura se virar requisito.

## Critério de pronto (DoD do Bloco 3)

- [ ] `just type` verde
- [ ] `just lint` verde
- [ ] `just format-check` verde
- [ ] `just test-unit` verde com Bloco 3 testes
- [ ] Smoke no Swagger: upload de PDF jurídico → `status=embedded`
- [ ] `GET /providers` retorna 1 ou 2 itens dependendo de OPENAI_API_KEY
- [ ] Reupload do mesmo arquivo retorna `was_already_ingested=true`
- [ ] Upload de arquivo > 10MB retorna 413
- [ ] Upload de binário desconhecido retorna 422

## Commit sugerido

```powershell
git add -A
git commit -m "feat(sprint3-bloco3): embeddings dual + chroma + ingestion pipeline"
git push
```

## Próximo: Bloco 4

- `RetrievalUseCase` (embed query + busca no Chroma com top_k + threshold)
- `AnswerUseCase` (retrieval + prompt jurídico + LLM + citações)
- `OpenAiLlmClient` (gpt-4o-mini com cálculo de custo por token)
- Router `/api/v1/queries`
- DoD final da Sprint 3: pergunta sobre cláusula → resposta com 3 fontes em ≤ 3s
