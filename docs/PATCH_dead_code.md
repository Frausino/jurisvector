# Patch trivial — remover dead code em `deps.py` (gap #2)

A função `resolve_embedder_for_provider` foi adicionada em alguma
iteração anterior e nunca foi referenciada por nenhum router.
`grep -rn resolve_embedder_for_provider src/ tests/` confirma que só
aparece na própria definição.

## Edição

Em `src/docuvector/api/deps.py`, remover:

```python
def resolve_embedder_for_provider(
    provider_name: EmbeddingProviderName,
) -> EmbeddingProvider:
    return resolve_embedder(provider_name)
```

E, se sobrar import órfão de `EmbeddingProvider` ou
`EmbeddingProviderName`, removê-los também.

## Comando rápido

```bash
## remove a função (substitua N pela linha real onde começa o def)
grep -n "def resolve_embedder_for_provider" src/docuvector/api/deps.py
## edite manualmente a partir daí; é mais seguro que sed multilinha.
```

## Validação pós-edição

```bash
just lint
## ruff vai pegar `EmbeddingProvider` e `EmbeddingProviderName` órfãos se
## você esquecer de remover do import (F401).
```
