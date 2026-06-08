# Metodologia Experimental — JurisVector

**Documento:** Metodologia de avaliação da compressão de embeddings
**Autor:** Davi Rosa F. e Breno Manoel
**Contexto:** TCC — Desenvolvimento de Sistemas, CEUB 2026

---

## 1. Objetivo experimental

Avaliar empiricamente o impacto da compressão de embeddings na qualidade do retrieval semântico em um corpus jurídico, usando a coleção original (float32) como baseline.

**Pergunta central:** A compressão degrada o retrieval a ponto de comprometer a qualidade da resposta RAG gerada?

---

## 2. Configuração experimental

### Corpus
- Documentos jurídicos em PDF ou TXT (contratos, petições, NDAs, sentenças)
- Embedding: `intfloat/multilingual-e5-small` (384 dimensões)
- Chunking: RecursiveSplitter, chunk_size=512, overlap=64

### Coleções avaliadas

| ID | Método | Dims | Tipo |
|---|---|---|---|
| original | Nenhum (baseline) | 384 | float32 |
| int8 | Quantização Int8 | 384 | int8 |
| binary | Binary packbits | 384 | uint8 |
| rp | Random Projection | 192 | float32 |
| pca | PCA global | 192 | float32 |

### Parâmetros fixos
- `top_k = 5`
- `similarity_threshold = 0.0` (sem filtro no modo comparativo)
- Embedder: sentence_transformers em todos os testes

---

## 3. Métricas de Information Retrieval

### 3.1 Recall@K

Fração dos documentos relevantes (baseline) recuperados pela coleção comprimida.

```
Recall@K = |docs_comprimidos ∩ docs_originais| / |docs_originais|
```

**Implementação:** deduplicação de `document_id` antes do cálculo para evitar dupla contagem de chunks do mesmo documento. Cap em 1.0.

### 3.2 Precision@K

Fração dos K resultados retornados que são relevantes.

```
Precision@K = |docs_comprimidos ∩ docs_originais| / |unique_retrieved|
```

### 3.3 MRR (Mean Reciprocal Rank)

Recíproco da posição do primeiro documento relevante.

```
MRR = 1 / rank_primeiro_relevante
```

MRR = 1.0 → relevante na posição 1. MRR = 0.5 → relevante na posição 2.

**Referência:** Manning, Raghavan, Schütze (2008). *Introduction to Information Retrieval*. Cambridge. Cap. 8.

---

## 4. Ground truth

O ground truth é definido como o conjunto de documentos recuperados pela **coleção original** (float32, sem compressão) para cada query.

**Justificativa:** a coleção original representa o estado sem degradação por compressão. As métricas medem fidelidade ao baseline, não relevância absoluta (que exigiria anotação humana, fora do escopo do TCC).

**Limitação declarada:** fidelidade ao baseline ≠ qualidade semântica absoluta. Um sistema pode ter Recall@K = 100% e ainda assim retornar documentos irrelevantes, se o baseline também os retornar.

---

## 5. Retenção semântica (benchmark de compressão)

Calculada pelo `CompressionBenchmarkUseCase` como correlação de Pearson entre as matrizes de similaridade coseno dos embeddings originais e comprimidos.

```
retention = Pearson(S_original, S_compressed)

onde S[i,j] = cosine_similarity(v_i, v_j)
```

**Decisão:** correlação de matrizes de similaridade (não de normas), pois captura a preservação de relações entre vetores, não apenas de magnitudes.

---

## 6. Limitações documentadas

| Limitação | Impacto | Decisão |
|---|---|---|
| PCA com corpus pequeno resulta em dims=1 | Compressão inútil, exibida como alerta no dashboard | Documentada; mínimo 10 chunks recomendado |
| PCA não serializado em disco | Re-treina a cada restart | Aceito no TCC; joblib seria a solução em produção |
| Ground truth = baseline (não humano) | Não mede relevância real | Documentado explicitamente |
| Recall@K por document_id, não chunk_id | Chunks diferentes do mesmo doc contam como 1 | Correto para medir cobertura de documentos |
| top_k=5 fixo no modo comparativo | Não varia K | Suficiente para demonstração didática |

---

## 7. Reprodutibilidade

- Random Projection: `seed=42` fixo — mesma matriz entre execuções
- PCA: `model_hash` (SHA-256 dos componentes) registrado no log
- Embedder: modelo fixo por coleção — configurável via env
- Banco: PostgreSQL com migrations versionadas (Alembic)
- Ambiente: `uv.lock` garante versões exatas de todas as dependências
