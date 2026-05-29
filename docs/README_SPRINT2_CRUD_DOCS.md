# Bloco 1 — CRUD de Documentos (fechamento honesto da Sprint 2)

Pacote que entrega o item faltante do DoD original da Sprint 2:
> "Pessoa loga, faz CRUD, user1 não vê doc de user2, admin vê tudo."

Upload (POST) NÃO entra aqui: depende do `IngestionUseCase` que sai
no Bloco 3 da Sprint 3.

## Estrutura

Os caminhos refletem onde os arquivos devem ficar no projeto.

```
sprint2-crud-docs/
├── src/docuvector/
│   ├── application/
│   │   └── document_crud_use_case.py        [NOVO]
│   ├── api/
│   │   ├── deps.py                          [SUBSTITUI]
│   │   ├── routers/
│   │   │   └── documents.py                 [NOVO]
│   │   └── schemas/
│   │       └── documents.py                 [NOVO]
│   └── main.py                              [SUBSTITUI]
└── tests/
    ├── unit/application/
    │   └── test_document_crud_use_case.py   [NOVO]
    └── integration/
        └── test_document_crud.py            [NOVO]
```

## Como aplicar

```powershell
git checkout feature/sprint-3-rag-domain
# ou cria uma branch dedicada se preferir separar:
# git checkout -b feature/sprint-2-crud-docs

# Extrai dentro do repositório (na raiz). Os caminhos casam.
Expand-Archive -Path .\sprint2-crud-docs.zip -DestinationPath . -Force

# Confere diff
git status
git diff --stat            # esperado: 2 substituídos + 4 novos = 6 arquivos

# Gates estáticos
just lint
just format-check
just type

# Testes unit (não precisam de banco)
just test-unit             # esperado: existentes + 7 novos do crud verdes

# Sobe banco e roda integration
just up
just migrate-status        # esperado: 0003_documents_and_chunks (head)
just test-integration      # esperado: existentes + 7 novos verdes

# CI completo
just ci

# Smoke no Swagger
just dev
# Acesse http://127.0.0.1:8000/docs
# Verifique que apareceu a seção "documents" com 3 endpoints
```

## Suíte de testes integration

Cobre os 4 cenários BOLA obrigatórios mais 3 cenários de borda:

1. `test_list_documents_returns_only_owned_items` — listagem nunca traz docs alheios
2. `test_list_documents_requires_authentication` — 401 sem Bearer
3. `test_get_document_returns_owned_resource` — fluxo feliz
4. `test_get_document_of_another_user_returns_404_not_403` — anti-enumeração + audit
5. `test_get_document_with_random_id_returns_404` — id inexistente também é 404
6. `test_delete_document_succeeds_for_owner_and_audits` — delete + audit
7. `test_delete_document_of_another_user_returns_404_and_preserves_resource` — cross-tenant delete não apaga e não vaza

## Decisões arquiteturais aplicadas

1. **Mascaramento RGN-10:** tentativa cross-tenant retorna 404, igual a
   inexistência. Indistinguível na resposta HTTP. Diferenciação fica
   no audit log para investigação interna.

2. **`list_for_owner` não emite audit log.** Leitura de catálogo
   próprio é operação rotineira; auditar geraria volume sem benefício
   investigativo. Get e Delete (acessos específicos) são auditados.

3. **`POST /documents` ficou de fora deste bloco.** Criar um stub que
   não ingere seria mentira. O endpoint sai junto com o
   `IngestionUseCase` no Bloco 3 da Sprint 3.

4. **Audit `failure` em vez de `forbidden` no get/delete negado.**
   Detectar tentativas cross-tenant exige ler documentos de outros
   donos no use case, o que quebraria a fronteira de ownership do
   repositório. Marcar tudo como `failure` é a opção segura.
   Auditoria administrativa futura (com permissão dedicada) pode
   correlacionar eventos suspeitos por IP/timestamp.

5. **`DocumentListResponse` com `items` + `total`.** Wrap explícito em
   vez de array cru. Permite evoluir para paginação sem quebrar
   contrato. Recomendação OWASP API Security.

## Critério de pronto (DoD do Bloco 1)

- [ ] `just type` verde
- [ ] `just lint` verde
- [ ] `just test-unit` verde, 7 testes novos passando
- [ ] `just test-integration` verde, 7 testes novos passando
- [ ] Swagger mostra seção `documents` com GET list, GET id, DELETE id
- [ ] Audit logs em `audit_logs` carregam `document_deleted` e `access_denied`

## Commit sugerido

```powershell
git add -A
git commit -m "feat(sprint2-crud): documents CRUD with BOLA enforcement and audit"
git push
```

## Tag de fechamento da Sprint 2

Após Bloco 1 verde:
```powershell
git checkout develop
git pull
git tag -a v0.2.1-sprint2-complete -m "Sprint 2 completa: Auth + CRUD docs + BOLA"
git push origin v0.2.1-sprint2-complete
```
