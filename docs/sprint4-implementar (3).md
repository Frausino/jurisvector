# sprint4-implementar.md

Sprint 4A — Compressão observável (escopo reduzido, baixo risco, alto impacto)
Sprint 4B — Observabilidade econômica (posterior, maior complexidade)

Baseado na avaliação arquitetural do revisor (jun/2026) e no estado real do release.zip.

---

## Decisões de design incorporadas

### 1. Um único dataclass: `CompressionMetrics`

O plano anterior propunha `CompressionResult` no domínio + `CompressionMetrics` na
persistência. São quase idênticos. Decisão: **um único `CompressionMetrics` no domínio**,
usado do use case até o repositório. Menos duplicação, menos mapeamento, menos bugs.

### 2. Retenção semântica via Pearson de similaridades coseno (não de normas)

O plano anterior propunha `Pearson(||v||, ||v'||)` (correlação entre magnitudes).
Isso mede preservação de escala, não de semântica.

**Decisão correta:**

```
1. Para cada par (i, j) de chunks:
   cos_original[i,j]   = cosine_sim(v_i,  v_j)
   cos_compressed[i,j] = cosine_sim(v_i', v_j')

2. Achatar as matrizes triangulares superiores em vetores 1D
   (excluindo diagonal para evitar cos(v,v)=1 trivial)

3. semantic_retention = Pearson(cos_original, cos_compressed)
```

Isso mede se a **estrutura relativa** entre documentos foi preservada após compressão,
que é exatamente o que importa para RAG. Defensável diante de banca e pesquisadores.

Para documentos com muitos chunks (n > 200), amostrar aleatoriamente 200 pares
para manter o custo de O(n²) sob controle.

### 3. Sprint 4B separada

EmbeddingBenchmarkUseCase, MetricsUseCase, dashboard de KPIs e estimativas
econômicas (Pinecone/Qdrant em R$/mês) vão para Sprint 4B. São praticamente
um produto de observabilidade separado e não bloqueiam o diferencial principal.

---

## Sprint 4A — Escopo

### Bloco 1 — Domínio puro

**Arquivos criados:**
- `src/docuvector/domain/interfaces/compressor.py`
- `src/docuvector/domain/entities/compression_metrics.py`

**Arquivos editados:**
- `src/docuvector/domain/enums.py` → adicionar `CompressionMethod` enum
- `src/docuvector/domain/entities/document.py` → 5 campos opcionais

#### `compressor.py` — o quê e por quê

```python
class Compressor(Protocol):
    @property
    def method_name(self) -> CompressionMethod: ...
    @property
    def target_dim(self) -> int: ...
    def fit(self, vectors: ndarray) -> None: ...
    def transform(self, vectors: ndarray) -> ndarray: ...
```

`fit` e `transform` separados porque PCA e RandomProjection precisam de fit
em batch antes de transformar. Int8 e Binary são stateless; implementam `fit`
como no-op. Isso mantém a interface uniforme sem condicional no use case.

#### `compression_metrics.py` — o quê e por quê

```python
@dataclass(frozen=True, slots=True)
class CompressionMetrics:
    method: CompressionMethod
    original_dim: int
    compressed_dim: int
    ratio_bytes: float          # ex.: 4.0 para Int8 (float32→int8)
    fit_time_ms: int
    transform_time_ms: int
    semantic_retention: float   # Pearson de similaridades coseno [0, 1]
    n_vectors: int              # quantos chunks foram usados no benchmark
```

Único dataclass do sistema para métricas de compressão. Não há outro.
O repositório persiste campos individuais; o use case monta este objeto.

#### `CompressionMethod` enum

```python
class CompressionMethod(str, Enum):
    PCA = "pca"
    RANDOM_PROJECTION = "random_projection"
    INT8 = "int8"
    BINARY = "binary"
```

#### Campos adicionados em `Document`

```python
compression_method: CompressionMethod | None = None
original_dimension: int | None = None
compressed_dimension: int | None = None
semantic_retention: float | None = None
ingest_time_ms: int | None = None
```

`frozen=True` na entidade — para atualizar usa-se `dataclasses.replace(doc, ...)`.
Isso é o padrão já adotado no projeto (ver `update_status` no use case de ingestão).

---

### Bloco 2 — 4 Compressores concretos

**Arquivos criados:**
- `src/docuvector/infrastructure/compression/__init__.py`
- `src/docuvector/infrastructure/compression/pca_compressor.py`
- `src/docuvector/infrastructure/compression/random_projection_compressor.py`
- `src/docuvector/infrastructure/compression/int8_compressor.py`
- `src/docuvector/infrastructure/compression/binary_compressor.py`

Todos importam apenas `numpy`, `sklearn` e `scipy` — já estão no `pyproject.toml`.
Nenhum import de `docuvector.*` além do Protocol `Compressor` e do enum.

#### `PcaCompressor`
- `sklearn.decomposition.PCA(n_components=target_dim, svd_solver="full")`
- `fit`: chama `pca.fit(X)`.
- `transform`: chama `pca.transform(X)`, retorna `float32`.
- `ratio_bytes = original_dim / compressed_dim` (ambos float32 → mesmo dtype).
- Estado: guarda `self._pca` após fit. Levanta `RuntimeError` se `transform`
  for chamado sem `fit` antes.

#### `RandomProjectionCompressor`
- `sklearn.random_projection.GaussianRandomProjection(n_components=target_dim)`
- Mesmo padrão de PCA.
- `ratio_bytes = original_dim / compressed_dim`.

#### `Int8Compressor`
- Sem redução de dimensão: `compressed_dim == original_dim`.
- `fit`: no-op (stateless).
- `transform`: escala para `[-128, 127]` via `(X / max_abs) * 127`, converte
  para `int8`. Guarda `max_abs` no fit para consistência (se fit receber dados,
  usa o max deles; se chamado direto sem fit, usa max do próprio batch).
- `ratio_bytes = 4.0` (float32 = 4 bytes → int8 = 1 byte).

#### `BinaryCompressor`
- Sem redução de dimensão: `compressed_dim == original_dim`.
- `fit`: no-op.
- `transform`: `(X > 0).astype(uint8)`. Representa 1 bit por dimensão conceitualmente.
  Na prática retorna `uint8` (1 byte por dim) para manter interface uniforme de ndarray.
  `ratio_bytes = 32.0` (float32 = 32 bits → 1 bit = 32× economia teórica).
- Nota no docstring: redução **real** exigiria `numpy.packbits`; aqui usamos
  uint8 para facilitar a Pearson sem desempacotar. O ratio teórico ainda é válido.

---

### Bloco 3 — `VectorStore.get_vectors_for_document`

**Arquivos editados:**
- `src/docuvector/domain/interfaces/vector_store.py`
- `src/docuvector/infrastructure/vector_stores/chroma_vector_store.py`

#### Interface

```python
def get_vectors_for_document(
    self,
    owner_id: UUID,
    document_id: UUID,
) -> ndarray:
    """Retorna matriz (n_chunks, n_dims) dos embeddings do documento.

    Levanta DocumentNotFoundError se não houver vetores.
    Filtra por owner_id (defesa BOLA).
    """
```

#### ChromaDB

```python
result = self._collection.get(
    where={"$and": [
        {"owner_id": str(owner_id)},
        {"document_id": str(document_id)},
    ]},
    include=["embeddings"],
)
```

Retorna `numpy.array(result["embeddings"], dtype=numpy.float32)`.
Se `result["embeddings"]` for vazio, levanta `DocumentNotFoundError`.

**Por quê o filtro de `owner_id` é obrigatório:**
Sem ele, um usuário malicioso que conhece o `document_id` de outro consegue
extrair os embeddings via benchmark. BOLA se aplica também a leituras de vetor.

---

### Bloco 4 — `DocumentRepository.update_compression_metrics`

**Arquivos editados:**
- `src/docuvector/domain/interfaces/document_repository.py`
- `src/docuvector/infrastructure/persistence/document_repository_impl.py`

#### Interface

```python
def update_compression_metrics(
    self,
    owner_id: UUID,
    document_id: UUID,
    metrics: CompressionMetrics,
) -> Document:
    """Persiste métricas do melhor compressor. Filtra por owner_id (BOLA)."""
```

#### Implementação SQLAlchemy

`UPDATE documents SET compression_method=?, original_dimension=?,
compressed_dimension=?, semantic_retention=?, ingest_time_ms=?
WHERE id=? AND owner_id=?`

Retorna a entidade `Document` atualizada via `find_by_id_for_owner`.
Pattern idêntico ao `update_status` já existente — sem surpresa.

---

### Bloco 5 — `CompressionBenchmarkUseCase`

**Arquivo criado:**
- `src/docuvector/application/compression_benchmark_use_case.py`

#### Fluxo interno

```
1. find_by_id_for_owner(owner_id, document_id)
   → se não encontrado: DocumentNotFoundError
   → se status != EMBEDDED: levanta BenchmarkNotReadyError (novo)

2. get_vectors_for_document(owner_id, document_id)
   → ndarray shape (n_chunks, n_dims)

3. target_dim = request.target_dim or original_dim // 2

4. Para cada compressor em [PCA, RandomProjection, Int8, Binary]:
   a. t0 = perf_counter()
   b. compressor.fit(X)
   c. fit_time_ms = elapsed
   d. t1 = perf_counter()
   e. X_compressed = compressor.transform(X)
   f. transform_time_ms = elapsed
   g. semantic_retention = _compute_pearson_of_cosine_similarities(X, X_compressed)
   h. Monta CompressionMetrics

5. Seleciona best = max(results, key=lambda r: r.semantic_retention)

6. update_compression_metrics(owner_id, document_id, best)

7. audit_repository.append(DOCUMENT_UPDATED, metadata={
     "benchmark_type": "compression",
     "n_compressors": 4,
     "best_method": best.method.value,
     "best_retention": best.semantic_retention,
   })

8. Retorna list[CompressionMetrics] (todos os 4, ordenados por retention desc)
```

#### `_compute_pearson_of_cosine_similarities`

```python
def _compute_pearson_of_cosine_similarities(
    original: ndarray,
    compressed: ndarray,
    max_pairs: int = 200,
) -> float:
    """Pearson entre matrizes de similaridade coseno antes e depois.

    Se n_chunks > sqrt(max_pairs), amostra aleatoriamente max_pairs pares
    para manter custo O(n²) sob controle.
    """
    n = len(original)
    # Normaliza para vetores unitários (cosine via dot product)
    orig_norm = original / (numpy.linalg.norm(original, axis=1, keepdims=True) + 1e-8)
    comp_norm = compressed / (numpy.linalg.norm(compressed, axis=1, keepdims=True) + 1e-8)

    # Triangular superior sem diagonal: i < j
    idx_i, idx_j = numpy.triu_indices(n, k=1)
    if len(idx_i) > max_pairs:
        sample = numpy.random.choice(len(idx_i), max_pairs, replace=False)
        idx_i, idx_j = idx_i[sample], idx_j[sample]

    cos_orig = numpy.sum(orig_norm[idx_i] * orig_norm[idx_j], axis=1)
    cos_comp = numpy.sum(comp_norm[idx_i] * comp_norm[idx_j], axis=1)

    correlation, _ = scipy.stats.pearsonr(cos_orig, cos_comp)
    return float(numpy.clip(correlation, 0.0, 1.0))
```

`clip(0, 1)`: correlação negativa não faz sentido semântico aqui; retorna 0.

---

### Bloco 6 — Endpoint `POST /api/v1/documents/{id}/benchmark-compression`

**Arquivos editados:**
- `src/docuvector/api/routers/documents.py`
- `src/docuvector/api/schemas/documents.py`
- `src/docuvector/api/deps.py`

#### Schema de request

```python
class BenchmarkCompressionRequest(BaseModel):
    target_dim: int | None = Field(
        default=None,
        ge=2,
        description="Dimensão alvo. Se None, usa metade da dimensão original.",
    )
```

#### Schema de response

```python
class CompressorBenchmarkItem(BaseModel):
    method: CompressionMethod
    original_dim: int
    compressed_dim: int
    ratio_bytes: float
    fit_time_ms: int
    transform_time_ms: int
    semantic_retention: float
    n_vectors: int

class BenchmarkCompressionResponse(BaseModel):
    document_id: UUID
    results: list[CompressorBenchmarkItem]  # 4 itens, desc por semantic_retention
    best_method: CompressionMethod
    best_retention: float
    # Campos para o dashboard da Sprint 4B:
    original_storage_mb: float   # n_chunks × original_dim × 4 bytes
    best_storage_mb: float       # n_chunks × compressed_dim × bytes_per_element
    savings_pct: float           # (1 - best/original) × 100
```

`savings_pct` e os campos de storage são calculados no router (aritmética simples),
não no use case. Use case retorna só as métricas brutas.

#### Deps

```python
def provide_compression_benchmark_use_case(
    session: SessionDependency,
    settings: SettingsDependency,
) -> CompressionBenchmarkUseCase:
    ...

CompressionBenchmarkUseCaseDependency = Annotated[
    CompressionBenchmarkUseCase,
    Depends(provide_compression_benchmark_use_case),
]
```

---

### Bloco 7 — Testes

**Arquivos criados:**
- `tests/unit/infrastructure/test_pca_compressor.py`
- `tests/unit/infrastructure/test_random_projection_compressor.py`
- `tests/unit/infrastructure/test_int8_compressor.py`
- `tests/unit/infrastructure/test_binary_compressor.py`
- `tests/unit/application/test_compression_benchmark_use_case.py`
- `tests/integration/test_benchmark_endpoint.py`

#### Propriedades invariantes (hypothesis)

```python
@given(
    n=st.integers(min_value=4, max_value=50),
    d=st.integers(min_value=8, max_value=128),
)
def test_pca_compressed_dim_le_original(n, d):
    X = numpy.random.randn(n, d).astype(numpy.float32)
    c = PcaCompressor(target_dim=d // 2)
    c.fit(X)
    X_c = c.transform(X)
    assert X_c.shape[1] <= d

@given(...)
def test_semantic_retention_in_bounds(n, d):
    ...
    assert 0.0 <= retention <= 1.0

@given(...)
def test_ratio_bytes_positive(n, d):
    ...
    assert metrics.ratio_bytes > 0
```

#### Unit do use case

- `_FakeVectorStore` retorna matriz aleatória.
- `_FakeDocumentRepository` retorna documento fake com `status=EMBEDDED`.
- Verifica: 4 resultados, retention em [0,1], best gravado no repositório.

#### Integration

- Upload de TXT via TestClient.
- `POST /api/v1/documents/{id}/benchmark-compression`
- Verifica: `200`, `len(results) == 4`, `best_method` é um dos 4, `savings_pct > 0`.

---

## Arquivos que NÃO entram na Sprint 4A

- `application/embedding_benchmark_use_case.py` → Sprint 4B
- `application/metrics_use_case.py` → Sprint 4B
- `api/routers/metrics.py` → Sprint 4B
- `api/schemas/metrics.py` → Sprint 4B
- Cálculo de R$/mês Pinecone/Qdrant → Sprint 4B
- Templates Jinja2 → Sprint 5

---

## Ordem de implementação dentro da Sprint 4A

```
Bloco 1 (domínio puro: Protocol + CompressionMetrics + enum + Document)
    ↓
Bloco 2 (4 compressores concretos)
    ↓           ↓
Bloco 3    Bloco 4
(VectorStore)  (DocumentRepository)
    ↓           ↓
Bloco 5 (CompressionBenchmarkUseCase)
    ↓
Bloco 6 (endpoint)
    ↓
Bloco 7 (testes)
```

Blocos 3 e 4 são independentes entre si; podem ser feitos em qualquer ordem
ou em paralelo.

---

## Definition of Done Sprint 4A

- `just ci` verde.
- `POST /api/v1/documents/{id}/benchmark-compression` retorna os 4 compressores.
- `savings_pct > 0` na resposta.
- Colunas `compression_method`, `original_dimension`, `compressed_dimension`,
  `semantic_retention` preenchidas no banco após o benchmark.
- Testes hypothesis dos 4 compressores passando com ≥ 100 exemplos.
- Cobertura ≥ 70%.

## Frase de defesa (Sprint 4A)

"O endpoint de benchmark executa os 4 compressores sobre os embeddings reais
do documento. A retenção semântica é calculada via correlação de Pearson entre
as matrizes de similaridade coseno antes e depois da compressão — uma métrica
que mede preservação da estrutura relativa entre documentos, não apenas
preservação de escala. O sistema persiste o melhor resultado no banco e expõe
economia de armazenamento em percentual. Com um corpus de 1 milhão de chunks
em OpenAI ada-002 (1536 dimensões), a compressão PCA para 384 dimensões
representa 75% de economia de armazenamento — cerca de R$ X/mês em Pinecone
à cotação atual."
