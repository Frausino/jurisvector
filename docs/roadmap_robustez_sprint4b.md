# Plano de robustez pós-Sprint 4B

## Objetivo

Evoluir a base atual de benchmark, ingestão e métricas para um modo de operação que **não dependa de heurísticas locais**, não quebre em máquina nova, não trave por cold start de modelo, e não compartilhe estado frágil entre testes ou execuções concorrentes.

A meta não é apenas “passar no meu computador”. A meta é tornar o comportamento previsível em:
- máquina do desenvolvedor com cache vazio;
- CI/CD limpa;
- container efêmero;
- execução repetida com múltiplos testes de integração;
- crescimento do corpus e troca de provider.

---

## Diagnóstico resumido

1. O benchmark de embeddings hoje falha quando o primeiro carregamento do provider excede o timeout fixo. Isso é esperado em cold start de Sentence Transformers.
2. O Chroma persistente estava sendo tratado como recurso global de sessão e, em testes, isso causou estado compartilhado e erro de escrita readonly.
3. As queries de métricas já estão alinhadas com o schema atual, mas qualquer desvio entre enum do ORM, migration e SQL explode em tempo de execução.
4. O teste end-to-end mostrou que a estratégia correta é isolar diretório e ciclo de vida do storage por ambiente, não confiar em limpeza manual frágil.
5. A base já tem boa tipagem e cobertura, então o próximo salto é de **resiliência operacional**, não de sintaxe.

---

## Arquivos que devem absorver as mudanças

### 1) `src/docuvector/application/embedding_benchmark_use_case.py`

Problema atual:
- timeout fixo demais para cold start;
- benchmark mede carga do modelo + inferência ao mesmo tempo;
- primeiro uso pode cair em timeout mesmo quando o provider está saudável.

Mudanças recomendadas:
- separar **carregamento do provider** de **medição de inferência**;
- introduzir warmup explícito antes de medir;
- manter timeout distinto para `load` e para `inference`;
- registrar estado do provider para evitar repetir falhas cegamente.

Estratégia robusta:
- criar um warmup semântico curto, por exemplo `embed_query("warmup")`, fora da janela medida;
- usar timeout maior apenas para inicialização;
- usar timeout menor para inferência real;
- se o provider falhar em cold start, marcar como indisponível em vez de abortar toda a execução.

Pseudocódigo:

```python
provider = resolve_provider(...)
provider.warmup()
start = perf_counter()
vector = provider.embed_query(query)
latency_ms = perf_counter() - start
```

Por quê:
- benchmark passa a medir a qualidade do provider, não o tempo de baixar pesos;
- o resultado fica comparável entre máquinas e runners;
- o comportamento fica estável sob cache quente e cache frio.

---

### 2) `src/docuvector/infrastructure/embeddings/sentence_transformers_embedder.py`

Problema atual:
- o primeiro uso pode carregar pesos e tokenizer sob demanda;
- isso é aceitável em produção, mas precisa ser controlado;
- se o carregamento vive dentro do caminho crítico do benchmark, o timeout do benchmark vira ruído.

Mudanças recomendadas:
- tornar o carregamento do modelo explícito e cacheado;
- expor um método de warmup ou `ensure_loaded()`;
- separar “instanciar objeto” de “carregar pesos”.
- se possível, usar cache de processo com invalidation controlada.

Estratégia robusta:
- `get_sentence_transformer()` cacheado por processo;
- `embed_query()` chama o modelo já pronto;
- o benchmark chama `ensure_loaded()` antes de medir.

Por quê:
- cold start deixa de contaminar a métrica;
- o provider fica previsível mesmo com cache de HF vazio;
- evita timeout artificial em máquina nova ou CI.

---

### 3) `src/docuvector/api/deps.py`

Problema atual:
- providers e singletons vivem em um mesmo arquivo;
- Chroma e outros recursos são resolvidos como singletons de processo;
- em ambiente de teste isso induz estado compartilhado.

Mudanças recomendadas:
- decompor o wiring por bounded context, quando o arquivo crescer;
- manter `get_vector_store()` como singleton apenas onde fizer sentido operacional;
- introduzir um mecanismo de override explícito para testes;
- evitar que o teste precise limpar diretório manualmente em cada caso.

Estratégia robusta:
- provider de produção pode continuar cacheado;
- provider de teste deve usar persistência efêmera;
- o contrato do provider deve permitir a troca sem monkeypatch frágil.

Por quê:
- reduz acoplamento entre bootstrap e regra de negócio;
- permite CI limpo e execução repetida;
- facilita testar com backends diferentes.

---

### 4) `tests/conftest.py`

Problema atual:
- o ambiente de teste usa `CHROMA_PERSIST_DIR` fixo;
- a suíte compartilha estado de disco entre casos;
- a limpeza manual posterior pode brigar com cliente aberto.

Mudanças recomendadas:
- substituir diretório fixo por diretório temporário por sessão ou por teste;
- centralizar a criação do diretório em fixture;
- remover dependência de `shutil.rmtree()` dentro dos testes de integração.

Estratégia robusta:
- usar `tmp_path_factory` ou `tempfile.mkdtemp`;
- configurar `CHROMA_PERSIST_DIR` antes da criação do app;
- limpar somente no teardown da fixture responsável pelo ambiente.

Exemplo:

```python
@pytest.fixture(scope="session", autouse=True)
def test_env(tmp_path_factory):
    chroma_dir = tmp_path_factory.mktemp("chroma")
    os.environ["CHROMA_PERSIST_DIR"] = str(chroma_dir)
```

Por quê:
- cada execução de suíte pode ter storage isolado;
- evita lock/read-only por reuso de arquivo;
- remove uma classe inteira de bugs intermitentes.

---

### 5) `tests/integration/test_benchmark_compression.py`

Problema atual:
- o teste tinha cleanup manual do Chroma;
- isso foi útil para descobrir o bug, mas não é o estado final ideal.

Mudanças recomendadas:
- remover limpeza manual de diretório do próprio teste;
- depender do ambiente configurado em `conftest.py`;
- manter o teste focado no comportamento de benchmark, não em housekeeping.

Por quê:
- o teste fica menor e mais confiável;
- evita limpeza concorrente de arquivo aberto;
- separa claramente responsabilidade do ambiente de teste e responsabilidade do caso de uso.

---

### 6) `tests/integration/test_rag_end_to_end.py`

Problema atual:
- a mesma classe de risco do Chroma aparecia aqui;
- o teste estava usando limpeza manual do persist dir.

Mudanças recomendadas:
- igual ao benchmark: remover cleanup manual;
- deixar o ambiente de teste fornecer storage temporário;
- manter o teste focado no fluxo RAG, não no ciclo de vida do diretório.

Por quê:
- evita efeito colateral entre testes;
- elimina estado residual;
- reduz variabilidade na execução da suíte.

---

### 7) `src/docuvector/infrastructure/vector_stores/chroma_vector_store.py`

Problema atual:
- o client é persistente e precisa sobreviver ao uso normal;
- em ambiente efêmero precisa ser isolado;
- o caminho de persistência e o ciclo de vida precisam ser explícitos.

Mudanças recomendadas:
- documentar claramente se o store é “production persistent” ou “test ephemeral”;
- garantir que a criação do diretório ocorre antes do client;
- suportar path configurado por ambiente sem dependência de diretório relativo;
- considerar uma camada de bootstrap que crie o diretório quando necessário.

Boas práticas:
- nunca pressupor que `./data/...` existe;
- nunca assumir que a coleção pode ser reaproveitada entre suítes;
- tratar o client como recurso de vida controlada pelo ambiente.

Por quê:
- reduz readonly database;
- evita bug por cwd diferente;
- torna o comportamento previsível em CI.

---

### 8) `src/docuvector/application/metrics_use_case.py`

Problema atual:
- as queries já estão próximas do schema real, mas dependem de consistência rigorosa;
- qualquer divergência entre enum, coluna física e migration quebra o dashboard;
- o caso atual mostrou que o banco de teste e o caminho de execução precisam ficar em sincronia.

Mudanças recomendadas:
- centralizar os nomes de status válidos em constantes de domínio ou helper;
- evitar literais duplicados espalhados em SQL;
- revisar se as queries filtram `document_status` e `audit_status` corretamente;
- manter um teste de integração por query crítica do dashboard.

Boas práticas:
- se um valor de enum muda, a query e o teste devem mudar no mesmo PR;
- não misturar nomes de atributo ORM com nome físico da coluna sem documentar;
- validar cada query crítica com teste de regressão.

Por quê:
- evita “passa local, quebra no banco real”;
- reduz drift entre ORM, migration e dashboard;
- melhora auditabilidade.

---

## Estratégia de implementação por fases

### Fase 1 — Estabilidade do benchmark de embeddings
1. Separar warmup de inferência.
2. Elevar timeout apenas para cold start.
3. Introduzir estado de saúde do provider.
4. Tornar o benchmark determinístico no caso padrão.

### Fase 2 — Isolamento total do Chroma em testes
1. Tirar diretório fixo de `CHROMA_PERSIST_DIR`.
2. Usar diretório temporário por suite.
3. Eliminar limpeza manual nos testes.
4. Garantir que o app não compartilha estado residual.

### Fase 3 — Hardening do dashboard e métricas
1. Consolidar constantes de status válidos.
2. Revisar queries SQL e enums usados.
3. Manter testes de regressão para cada agregação.
4. Evitar literal SQL duplicado quando possível.

### Fase 4 — Desacoplamento do bootstrap
1. Separar providers por contexto.
2. Introduzir overrides explícitos para testes.
3. Manter cache apenas onde ele é seguro.
4. Garantir que o ambiente define o ciclo de vida do recurso.

---

## Ideia central

A aplicação não deve depender de:
- cache quente de máquina local;
- diretório persistente manualmente limpo;
- timeout fixo que assume hardware específico;
- heurística frágil para “achar” que o provider vai responder a tempo.

Ela deve:
- inicializar o provider uma vez;
- medir só o que interessa;
- isolar storage por ambiente;
- refletir o schema real do banco;
- falhar de forma previsível e explícita.

---

## Resultado esperado

Com essas mudanças, o sistema passa a ser robusto em:
- minha máquina;
- sua máquina;
- CI;
- container novo;
- cache vazio;
- execução repetida.

E o comportamento deixa de depender de coincidências de ambiente.
