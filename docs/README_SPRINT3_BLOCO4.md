# Sprint 3 — Bloco 4: Retrieval + Answer + LLM

Fecha a Sprint 3 com o pipeline RAG completo: **pergunta sobre cláusula
jurídica → resposta com fontes citáveis**.

## Estrutura

```
sprint3-bloco4/
├── src/docuvector/
│   ├── infrastructure/llm/
│   │   ├── __init__.py                                       [NOVO]
│   │   ├── pricing.py                                        [NOVO]
│   │   └── openai_llm_client.py                              [NOVO]
│   ├── application/
│   │   ├── prompts/
│   │   │   ├── __init__.py                                   [NOVO]
│   │   │   └── legal_prompt.py                               [NOVO]
│   │   ├── retrieval_use_case.py                             [NOVO]
│   │   └── answer_use_case.py                                [NOVO]
│   ├── api/
│   │   ├── deps.py                                           [SUBSTITUI]
│   │   │   (adiciona get_llm_client, get_vector_store,
│   │   │    provide_retrieval/answer; mantém o resto)
│   │   ├── routers/queries.py                                [NOVO]
│   │   └── schemas/queries.py                                [NOVO]
│   └── main.py                                               [SUBSTITUI]
│       (registra router queries + handler 502 LlmGenerationError)
└── tests/
    ├── unit/
    │   ├── application/
    │   │   ├── test_retrieval_use_case.py                    [NOVO]
    │   │   └── test_answer_use_case.py                       [NOVO]
    │   └── infrastructure/
    │       └── test_legal_prompt.py                          [NOVO]
    └── integration/
        └── test_rag_end_to_end.py                            [NOVO]
            (upload → ask → resposta com fontes; LLM mockado)
```

## Decisões arquiteturais (todas confirmadas lendo o estado real do ZIP)

### 1. Vector store singleton via `@lru_cache`
O `ChromaVectorStore` mantém pool/conexão interna. Construir um por
request é caro e fragmenta o cache. `get_vector_store()` no `deps.py`
é singleton de processo, igual a outros recursos pesados (LLM, token
service).

### 2. `OpenAiLlmClient` também é singleton
O SDK da OpenAI mantém pool HTTP. Reusar a instância evita renegociar
TLS a cada chamada. Retry fica delegado ao SDK (`max_retries=3`),
não reimplementado aqui.

### 3. Prompt jurídico em PT-BR com citações `[1]`, `[2]`
Sem citações inline, a resposta é inútil para uso forense. O prompt
exige citação e instrui o LLM a usar uma frase CANÔNICA de abstenção
quando não tem contexto suficiente. O `AnswerUseCase` detecta essa
frase (case-insensitive) e marca `grounded=False` para o front
exibir indicador de baixa confiança.

### 4. Audit log centralizado no AnswerUseCase
Uma pergunta = um evento `QUERY_EXECUTED`. Metadata carrega tokens,
custo, latência, modelo, sources_count, grounded, embedding_provider.
`actor_user_id=owner_id` (snapshot completo virá quando middleware de
correlation_id chegar; hoje é None).

### 5. Detecção de `grounded` por frase canônica
Mais robusto que parsing de JSON estruturado (que falha em ~5% das
chamadas do gpt-4o-mini). Trade-off documentado no `legal_prompt.py`.

### 6. RAG defesa BOLA mantida
`RetrievalUseCase.retrieve(owner_id=...)` propaga direto para o
`VectorStore.search`, que sempre filtra por `owner_id` no Chroma.
Sem caminho que ignore o dono.

### 7. AskInput compacto
O `AnswerUseCase.ask` recebe um único dataclass `AskInput` em vez de
6+ argumentos posicionais. Mais legível e extensível (correlation_id,
overrides de top_k/threshold já estão lá).

### 8. Rate limit `/queries/ask` reusa `login_rate_limit_per_minute`
Decisão pragmática: não criar variável nova no Settings (que exigiria
sprint de migração). LLM é caro como bcrypt; teto comum faz sentido.
Polish futuro: variável dedicada `QUERY_RATE_LIMIT_PER_MINUTE`.

### 9. Handler 502 para `LlmGenerationError`
LLM upstream falhou → 502 Bad Gateway com mensagem genérica. Audit
já registrou a falha completa (com correlação ao usuário). Cliente
não vê detalhes internos da OpenAI.

### 10. Teste integration com LLM mockado via `dependency_overrides`
Chamar OpenAI real custa dinheiro, é não-determinístico e exige rede
no CI. Embedder local (E5) é REAL no teste — é a parte semântica
não-trivial; mockar tiraria a confiança. Marcado `@pytest.mark.slow`
para excluir do gate padrão se necessário.

## Como aplicar

```powershell
git checkout feature/sprint-3-rag-domain
Expand-Archive -Path .\sprint3-bloco4.zip -DestinationPath . -Force

just sync          # caso openai SDK precise rehash
just lint
just format-check
just type
just test-unit
just up
just migrate
just seed-admin
just test-integration  # demora ~30s (carrega E5 model na primeira vez)
just ci
```

## Smoke manual no Swagger

```
1. POST /api/v1/auth/login               → pega token
2. Authorize (cadeado)                    → cola token
3. POST /api/v1/documents                 → upload PDF/TXT jurídico
   - embedding_provider: sentence_transformers
4. POST /api/v1/queries/ask
   {
     "query": "Qual o prazo de rescisão?",
     "embedding_provider": "sentence_transformers"
   }
5. Resposta esperada: { answer, sources: [...], grounded: true, ... }
```

## DoD Sprint 3

- [ ] `just type` verde
- [ ] `just lint` verde
- [ ] `just test-unit` verde (3 suítes novas: retrieval + answer + prompt)
- [ ] `just test-integration` verde (test_rag_end_to_end)
- [ ] Upload contrato → pergunta sobre cláusula → resposta com >= 1 fonte
- [ ] Latência total ≤ 3s (com embedder local + gpt-4o-mini)
- [ ] Audit log mostra evento `query_executed` com tokens/custo/latência
- [ ] Pergunta tangencial → resposta marca `grounded=false`
- [ ] Tag `v0.3.0-sprint3` aplicada

## Pendências cientes (NÃO bloqueiam a Sprint 3)

1. **`query_rate_limit_per_minute` dedicado** no Settings (hoje
   reusa login).
2. **Middleware de `correlation_id`** gerando UUID por request HTTP e
   propagando para todos os use cases (entidade já suporta).
3. **Dashboard /metrics/dashboard** lendo audit_logs.metadata para
   exibir custo acumulado, latência p50/p95 por provider (Sprint 4).
4. **Tiktoken para token count exato** (hoje vem do `usage.total_tokens`
   da OpenAI — exato; mas em `LlmClient` futuros pode ser estimado).

## Frases para a banca

> "O pipeline de RAG é orquestrado em duas camadas: RetrievalUseCase
> faz busca semântica com filtro `owner_id` no Chroma; AnswerUseCase
> compõe retrieval + prompt jurídico + LLM e centraliza o audit log.
> Separação respeitada — retrieval não conhece LLM, LLM não conhece
> Chroma — graças aos Protocols do domínio."

> "O prompt jurídico exige citações inline `[1]`, `[2]` e instrui o
> modelo a usar uma frase exata de abstenção quando não tem contexto
> suficiente. O AnswerUseCase detecta essa frase e marca a resposta
> como `grounded=false`. O front exibe indicador de baixa confiança,
> e o usuário sabe quando NÃO confiar."

> "Custos, tokens e latência de cada pergunta vão para o audit log
> em `metadata`. Na Sprint 4, o dashboard de indicadores consome
> exatamente esses campos — sem schema adicional, sem outra fonte
> de verdade."

## Commit sugerido

```powershell
git add -A
git commit -m "feat(sprint3-bloco4): retrieval + answer + llm = closes sprint 3"
git tag v0.3.0-sprint3
git push --tags
```
