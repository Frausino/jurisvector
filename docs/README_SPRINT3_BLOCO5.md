# Sprint 3 — Bloco 5: LLM como provider pluggable

Refatora o RAG para que o usuário escolha o provider de LLM por
request, igual já escolhe o provider de embedding. Sem singleton fixo,
sem vendor lock-in, sem código de cloud no domínio.

## O macro

**Antes:**
```
AskRequest → resolve embedder → AnswerUseCase(llm_client=SINGLETON_OPENAI)
                                        ↓
                                  OpenAiLlmClient (fixo)
```

**Depois:**
```
AskRequest{embedding_provider, llm_provider}
   ↓
router resolve embedder (factory existente)
router resolve LLM client (factory NOVA)
   ↓
AnswerUseCase.ask(ask_input, llm_client=...)  # explicit, sem fallback
   ↓
audit_log.metadata = {..., "llm_provider": "ollama|openai|mock"}
```

`AnswerUseCase` fica stateless quanto ao vendor. Use case passa do
domínio direto para a métrica de auditoria, e a banca consegue ver no
audit_log qual provider gerou cada resposta.

## Estrutura

```
sprint3-bloco5/
├── src/docuvector/
│   ├── domain/
│   │   └── enums.py                                          [SUBSTITUI]
│   │       (+ LlmProviderName: OPENAI, OLLAMA, MOCK)
│   ├── config/
│   │   └── settings.py                                       [SUBSTITUI]
│   │       (+ LLM_DEFAULT_PROVIDER, OLLAMA_BASE_URL,
│   │          OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS)
│   ├── infrastructure/llm/
│   │   ├── __init__.py                                       [SUBSTITUI]
│   │   ├── mock_llm_client.py                                [NOVO]
│   │   ├── ollama_llm_client.py                              [NOVO]
│   │   └── factory.py                                        [NOVO]
│   │       (resolve_llm_client, list_available_providers)
│   ├── application/
│   │   └── answer_use_case.py                                [SUBSTITUI]
│   │       (ask() recebe llm_client explícito; AskInput
│   │        ganha campo llm_provider obrigatório)
│   └── api/
│       ├── deps.py                                           [SUBSTITUI]
│       │   (remove get_llm_client/provide_llm_client;
│       │    provide_answer_use_case fica sem llm_client)
│       ├── schemas/queries.py                                [SUBSTITUI]
│       │   (+ llm_provider em AskRequest;
│       │    + LlmProviderOption/LlmProviderListResponse;
│       │    + llm_provider em AnswerResponse)
│       └── routers/queries.py                                [SUBSTITUI]
│           (resolve LLM por request +
│            GET /api/v1/queries/llm-providers)
├── tests/
│   ├── unit/
│   │   ├── application/
│   │   │   └── test_answer_use_case.py                       [SUBSTITUI]
│   │   │       (novo contrato: ask recebe llm_client)
│   │   └── infrastructure/
│   │       ├── test_mock_llm_client.py                       [NOVO]
│   │       ├── test_ollama_llm_client.py                     [NOVO]
│   │       └── test_llm_factory.py                           [NOVO]
│   └── integration/
│       └── test_rag_end_to_end.py                            [SUBSTITUI]
│           (usa llm_provider="mock" no body em vez
│            de dependency_overrides; novo teste
│            de GET /llm-providers)
└── env.snippet                                               [NOVO]
    (variáveis para anexar ao .env)
```

## Decisões arquiteturais

### 1. LLM resolvido por request, não por singleton
O router lê `payload.llm_provider`, chama `resolve_llm_client(...)` e
passa explicitamente para `AnswerUseCase.ask`. Sem fallback escondido,
sem singleton no `__init__`. Isso fecha de vez o padrão problemático
de "DI quebrada por instância manual" identificado nas lições.

### 2. Factory espelha o padrão de embeddings
`infrastructure/llm/factory.py` é cópia conceitual de
`infrastructure/embeddings/factory.py`: `@lru_cache` por provider,
`list_available_providers` condicional a `OPENAI_API_KEY`. Consistência
arquitetural pesa para o leitor humano.

### 3. `httpx` direto para Ollama, sem SDK
Endpoint único (`POST /api/chat`), payload trivial. Adicionar
dependência `ollama-python` por 1 chamada seria over-engineering.

### 4. `MockLlmClient` detecta contexto pelo marcador do prompt
O `build_user_prompt` produz cabeçalhos canônicos ("Trechos de
documentos disponíveis para consulta:" ou "Nenhum trecho de documento
foi recuperado"). O Mock detecta esses marcadores e devolve a resposta
compatível com a detecção de `grounded=False` do `AnswerUseCase`.
Determinístico, zero rede, zero custo.

### 5. `OPENAI_API_KEY` faltando: falha NA factory, não no `complete()`
`resolve_llm_client(OPENAI)` levanta `LlmGenerationError` imediatamente.
Isso vira 502 no router com mensagem clara ("OPENAI_API_KEY não está
configurada"). Melhor que construir o cliente e quebrar 100ms depois.

### 6. `OLLAMA` sempre listado em `/llm-providers`
A UX deve permitir tentar. Indisponibilidade do servidor vira 502 com
mensagem clara no momento da chamada real. Ocultar do select exigiria
health-check síncrono que atrasaria toda página de configuração.

### 7. Default `LLM_DEFAULT_PROVIDER=mock` em dev/test
CI roda sem rede e sem chave. Em produção local: `ollama`. Em uso
premium: `openai`. A escolha é por variável de ambiente, não código.

### 8. `cost_usd=0` para Ollama e Mock
Sprint 4 pode mapear custo em watt-hora ou tempo de máquina, mas isso
é outra dimensão. Hoje, `cost_usd` é custo monetário direto.

## Como aplicar

```powershell
git checkout feature/sprint-3-rag-domain
Expand-Archive -Path .\sprint3-bloco5.zip -DestinationPath . -Force

# 1) Adicione as variáveis do env.snippet ao seu .env
Get-Content env.snippet | Add-Content .env

# 2) Sync deps (httpx já estava lá; nada novo)
just sync

# 3) Sanidade
just lint
just format-check
just type
just test-unit
just test-integration  # usa llm_provider=mock; não precisa de Ollama
just ci
```

## Smoke manual no Swagger

```
1. POST /api/v1/auth/login                → token
2. Authorize (cadeado)                     → cola token
3. GET  /api/v1/queries/llm-providers      → vê quais providers existem
4. POST /api/v1/documents                  → upload de PDF/TXT
5. POST /api/v1/queries/ask
   {
     "query": "Qual o prazo de rescisão?",
     "embedding_provider": "sentence_transformers",
     "llm_provider": "mock"          # ou "ollama" se estiver rodando
   }
6. Resposta esperada:
   {
     "answer": "[MOCK] Resposta determinística com base no trecho [1]...",
     "sources": [...],
     "grounded": true,
     "llm_provider": "mock",
     "model": "mock",
     "tokens_used": 0,
     "cost_usd": 0.0,
     ...
   }
```

## Como usar Ollama (modo local)

```bash
# 1) Instalar
curl -fsSL https://ollama.com/install.sh | sh

# 2) Baixar o modelo padrão
ollama pull qwen2.5:7b
# ou (máquina fraca):
ollama pull llama3.2:3b

# 3) Servir
ollama serve  # roda em http://localhost:11434

# 4) Mudar default no .env:
LLM_DEFAULT_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b

# 5) Reiniciar a API
just dev
```

## DoD do Bloco 5

- [ ] `just type` verde
- [ ] `just lint` verde
- [ ] `just test-unit` verde (3 suítes novas + answer_use_case refatorado)
- [ ] `just test-integration` verde sem precisar de chave/rede (usa mock)
- [ ] `GET /api/v1/queries/llm-providers` devolve `mock` e `ollama` por
      default; inclui `openai` apenas se `OPENAI_API_KEY` está setada
- [ ] `POST /ask` com `llm_provider="mock"` devolve `model="mock"`,
      `cost_usd=0`, `tokens_used=0`
- [ ] audit_log carrega `llm_provider` em `metadata`

## Frases para a banca

> "Separei completamente o provedor de embeddings do provedor de LLM.
> O usuário escolhe cada um independentemente: pode rodar tudo local
> com sentence-transformers + Ollama, sem custo e sem dados saindo
> da máquina; pode subir para OpenAI quando precisar de mais
> qualidade; ou usar o Mock para CI."

> "O `AnswerUseCase` recebe o `LlmClient` no método `ask()`, não no
> construtor. O router resolve por request a partir do campo
> `llm_provider` do payload. Sem singleton fixo, sem fallback
> escondido. Isso me deixa alternar providers em runtime sem reiniciar
> o processo."

> "Custos, tokens e provider de cada pergunta vão para o `audit_log.metadata`.
> Na Sprint 4, o dashboard de indicadores consome esses campos
> diretamente — sem schema adicional, sem outra fonte de verdade."

## Pendências cientes (NÃO bloqueiam a Sprint 3)

1. **`query_rate_limit_per_minute` dedicado** no Settings (hoje reusa login).
2. **Middleware de `correlation_id`** por request HTTP (entidade já suporta).
3. **Health-check de Ollama** em background para popular o select com status real.
4. **Adapters adicionais** (LM Studio, vLLM, HuggingFace Inference): só na Sprint 5.

## Commit sugerido

```powershell
git add -A
git commit -m "feat(sprint3-bloco5): LLM como provider pluggable (mock + ollama + openai)"
git push
```
