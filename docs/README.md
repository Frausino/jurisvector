# Sprint 3 — Bloco 5 — Pacote de Fixes da Auditoria

Pacote complementar ao `sprint3-bloco5.zip`. Resolve os 7 gaps
identificados na auditoria interna, **sem invalidar o pacote
principal** (que continua aplicável da forma como está).

## Resumo da auditoria

| # | Gap | Severidade | Origem | Resolvido por |
|---|-----|------------|--------|---------------|
| 1 | 2 Limiters concorrentes (auth + queries); main.py só registra um | 🔴 ALTO | pré-existente | `PATCH_limiter_unico.md` + `src/docuvector/api/limiting.py` |
| 2 | `resolve_embedder_for_provider` é dead code em `deps.py` | 🟡 MÉDIO | pré-existente | `PATCH_dead_code.md` (edição manual) |
| 3 | Markers do prompt duplicados entre `mock_llm_client.py` e `legal_prompt.py` | 🟡 MÉDIO | introduzido no bloco 5 | `src/docuvector/application/prompts/legal_prompt.py` + `src/docuvector/infrastructure/llm/mock_llm_client.py` |
| 4 | Factory sem função pública pra reset de cache | 🟡 BAIXO | introduzido | `src/docuvector/infrastructure/llm/factory.py` + `__init__.py` |
| 5 | Teste importava `_build_*_client` (private) | 🟡 BAIXO | introduzido | `tests/test_llm_factory.py` |
| 6 | `httpx.post` sem reuso de conexão | 🟡 BAIXO | introduzido | NÃO incluído (polish Sprint 4) |
| 7 | `conftest.py` não fixa `LLM_DEFAULT_PROVIDER=mock` | 🔴 ALTO | introduzido + projeto | `PATCH_conftest.md` (edição manual) |

Os gaps 1, 2 e 7 exigem **edição manual** porque alterar `main.py`,
`auth.py`, `deps.py` ou `conftest.py` em pacote .zip de substituição
total tem alto risco de pisar em modificações locais que o usuário
fez. Instruções estão nos `PATCH_*.md`.

Os gaps 3, 4 e 5 são entregues como **substituição de arquivos** no
pacote, porque os arquivos pertencem 100% ao Bloco 5.

## Estrutura

```
sprint3-bloco5-fixes/
├── README.md                                                # este arquivo
├── PATCH_conftest.md                                        # gap #7
├── PATCH_dead_code.md                                       # gap #2
├── PATCH_limiter_unico.md                                   # gap #1
├── src/docuvector/
│   ├── api/
│   │   └── limiting.py                                      # NOVO (gap #1)
│   ├── application/prompts/
│   │   └── legal_prompt.py                                  # SUBSTITUI (gap #3)
│   └── infrastructure/llm/
│       ├── __init__.py                                      # SUBSTITUI (gap #4)
│       ├── factory.py                                       # SUBSTITUI (gap #4)
│       └── mock_llm_client.py                               # SUBSTITUI (gap #3)
└── tests/
    └── test_llm_factory.py                                  # SUBSTITUI em tests/unit/infrastructure/ (gap #5)
```

## Ordem de aplicação recomendada

```powershell
## 1) Aplica o ZIP principal do Bloco 5 (se ainda não aplicou)
Expand-Archive -Path .\sprint3-bloco5.zip -DestinationPath . -Force

## 2) Aplica os fixes (substitui 5 arquivos + cria limiting.py)
Expand-Archive -Path .\sprint3-bloco5-fixes.zip -DestinationPath . -Force

## 3) Mova o teste pra pasta correta
Move-Item -Path .\tests\test_llm_factory.py `
          -Destination .\tests\unit\infrastructure\test_llm_factory.py `
          -Force

## 4) Lê e aplica os 3 PATCH_*.md manualmente:
##    - PATCH_conftest.md       → tests/conftest.py
##    - PATCH_dead_code.md      → src/docuvector/api/deps.py
##    - PATCH_limiter_unico.md  → auth.py, queries.py, main.py

## 5) Valida
Get-ChildItem -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force
just lint
just type
just test-unit
just test-integration
just ci
```

## Frase para a banca

> "Depois de implementar o Bloco 5, fiz uma auditoria do meu próprio
> pacote contra o estado real do projeto. Encontrei sete gaps,
> incluindo dois pré-existentes que não eram do bloco mas que valia
> corrigir: rate-limit fragmentado entre dois `Limiter` independentes
> e dead code em `deps.py`. Corrigi também dois pontos de
> acoplamento que eu mesmo introduzi: duplicação de constantes entre
> prompt e mock, e teste acessando funções privadas da factory.
> Auditoria de código próprio é parte do processo, não etapa opcional."
