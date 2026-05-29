# Sprint 3 — Bloco 2: Extractors + Splitter

Pacote pronto para integrar ao repositório `docuvector-lite`, terceira
camada concreta do pipeline RAG. Implementa os contratos
`DocumentExtractor` e `TextSplitter` definidos no domínio (Sprint 3
Dia 1) e prepara o terreno para o Bloco 3 (embeddings + ingestão).

## Estrutura

```
sprint3-bloco2/
├── src/docuvector/infrastructure/
│   ├── extractors/
│   │   ├── __init__.py                  [NOVO]
│   │   ├── factory.py                   [NOVO]
│   │   ├── pdf_extractor.py             [NOVO]
│   │   └── text_extractor.py            [NOVO]
│   └── chunking/
│       ├── __init__.py                  [NOVO]
│       └── recursive_splitter.py        [NOVO]
└── tests/
    ├── fixtures/
    │   └── sample_contract.pdf          [NOVO] (PDF de 1 página)
    └── unit/infrastructure/
        ├── extractors/
        │   ├── test_factory.py          [NOVO]
        │   ├── test_pdf_extractor.py    [NOVO]
        │   └── test_text_extractor.py   [NOVO]
        └── chunking/
            └── test_recursive_splitter.py  [NOVO]
```

## Como aplicar

```powershell
# Branch da Sprint 3 (mesma do Dia 1)
git checkout feature/sprint-3-rag-domain

# Extrai dentro da raiz do projeto
Expand-Archive -Path .\sprint3-bloco2.zip -DestinationPath . -Force

# Confere diff
git status
git diff --stat            # 10 arquivos novos

# Gates estáticos
just lint
just format-check
just type

# Testes unit
just test-unit
# esperado: existentes + ~30 novos do Bloco 2 verdes
# cobertura no infrastructure/extractors e /chunking deve ficar ≥ 90%

# CI completo (não precisa do Postgres para esses testes)
just ci
```

## O que entra aqui

### Extractors

- **`PlainTextExtractor`** (TXT, MD): UTF-8 com fallback latin-1.
  Markdown passa cru para o splitter; LLM lida bem com sintaxe nativa.
- **`PyPdfExtractor`** (PDF): pypdf em modo não-estrito; rejeita PDFs
  criptografados explicitamente. Encapsula `PdfReadError` e `PyPdfError`
  em `DocumentExtractionError` de domínio.
- **`resolve_extractor(file_format)`**: factory + registry com singleton
  por processo. TXT e MD compartilham a mesma instância.

### Splitter

- **`RecursiveSplitter`** (default 1000/200): algoritmo recursivo por
  separadores em ordem decrescente de prioridade
  (`\n\n` → `\n` → `. ` → ` ` → ``). Implementação manual, sem
  dependência de LangChain. Validação de parâmetros em construtor
  (`chunk_size > 0`, `chunk_overlap < chunk_size`).

## Decisões arquiteturais aplicadas

1.  **Extractors recebem `bytes`, não path.** Mais seguro (nenhum
    extractor toca filesystem), mais testável, casa com o `UploadFile`
    do FastAPI.
2.  **Exceções de pypdf não vazam.** Tudo vira `DocumentExtractionError`
    com mensagem clara. Domínio fica desacoplado de pypdf.
3.  **PDFs criptografados são rejeitados.** Não fazemos brute force nem
    aceitamos senhas; processar conteúdo protegido criaria risco legal
    em ambiente jurídico.
4.  **Singleton de extractors via `lru_cache`.** São stateless; criar
    instância nova a cada chamada seria desperdício de CPU em
    `CryptContext`-equivalentes futuros.
5.  **Splitter sem dependência externa.** LangChain seria over-kill;
    algoritmo é didático e o controle total ajuda na defesa do TCC.
6.  **Overlap entre chunks adjacentes.** Necessário para queries que
    caem na fronteira entre dois chunks; mantém contexto semântico.
7.  **`chunk_size` em caracteres, não tokens.** Tiktoken adicionaria
    dependência por benefício marginal. O Bloco 3 (`IngestionUseCase`)
    pode calcular tokens à parte se precisar para audit de custo.

## Validações em smoke local (já executadas)

- Splitter empty → `[]` ✅
- Splitter texto curto → 1 chunk único ✅
- Splitter 1400 chars → 11 chunks com overlap aparente entre adjacentes ✅
- Splitter texto sem separadores (500 chars `'a'`) → 3 chunks de janela ✅
- PlainTextExtractor UTF-8 com `ção` → preservado ✅
- PlainTextExtractor latin-1 → `Cláusula` com á decoded correto ✅
- PyPdfExtractor + fixture `sample_contract.pdf` → texto extraído ✅
- PyPdfExtractor + bytes inválidos → `DocumentExtractionError` ✅
- Factory PDF → `PyPdfExtractor`, TXT/MD → `PlainTextExtractor`, singleton ✅

## Critério de pronto

- [ ] `just type` verde
- [ ] `just lint` verde
- [ ] `just format-check` verde
- [ ] `just test-unit` verde, ~30 testes novos passando
- [ ] Cobertura `infrastructure/extractors` ≥ 90%
- [ ] Cobertura `infrastructure/chunking` ≥ 90%

## Commit sugerido

```powershell
git add -A
git commit -m "feat(sprint3-bloco2): extractors pdf/text + recursive splitter"
git push
```

## Próximo: Bloco 3

Com extractors + splitter prontos, o Bloco 3 entrega:
- `OpenAiEmbedder` e `SentenceTransformersEmbedder` (com prefixos E5)
- `ChromaVectorStore` com filtro `owner_id` built-in
- `IngestionUseCase` orquestrando o pipeline inteiro
- `POST /api/v1/documents` (upload multipart com validação de MIME real)
