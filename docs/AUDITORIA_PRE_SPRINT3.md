# Auditoria Técnica Pré-Sprint 3 — DocuVector Lite

> **Documento de análise. Não contém alterações de código.**
> Auditoria de segurança, performance e arquitetura do estado atual (fim da Sprint 2 Dia 4), com plano de refatoração priorizado antes de avançar para o pipeline RAG.

**Versão:** 1.0
**Data:** 28/05/2026
**Escopo auditado:** 43 arquivos (domínio, aplicação, infraestrutura, apresentação, testes, infra Docker)
**Objetivo:** garantir que a fundação esteja sólida, segura e performática antes de escalar para RAG, compressão e benchmarks. Prioridade máxima: **nada pode travar durante a apresentação ao vivo.**

---

## 1. Sumário executivo

O código está em nível sólido para um trabalho acadêmico, com Clean Architecture bem aplicada, separação de camadas correta e DevSecOps real. A auditoria encontrou **14 achados**, sendo:

| Severidade | Quantidade | Natureza |
|---|---|---|
| P0 (crítico, pode travar a aula) | 2 | Performance de login bloqueante |
| P1 (alto, segurança ou correção) | 4 | Validação, índice, CORS, health |
| P2 (médio, robustez) | 5 | Tipos, transações, erro handling |
| P3 (baixo, polish) | 3 | Naming, consistência, documentação |

Nenhum achado é um defeito estrutural grave. A arquitetura está correta. Os achados P0 são de natureza operacional (latência) e têm correção simples e barata, que deve ser feita **antes** da Sprint 3 para não arrastar o problema.

A frase central da auditoria: **o sistema está bem desenhado, mas o caminho de login está caro demais para uma demo ao vivo, e isso precisa ser resolvido antes de adicionar a carga do RAG.**

---

## 2. Achados P0 — Críticos (resolver antes da Sprint 3)

### P0-1 — Login custa ~2x bcrypt cost 12, pode travar a demo

**Arquivo:** `src/docuvector/application/auth_use_case.py`
**Local:** `login()` + `_equalize_timing_against_enumeration()`

**Problema:**
O caminho de login com email inexistente executa:
1. `find_by_email` (query)
2. `_equalize_timing_against_enumeration` → na primeira chamada faz `hash()` (bcrypt cost 12 ≈ 250-400ms) **e** `verify()` (mais um bcrypt cost 12 ≈ 250-400ms)

E o caminho com senha errada executa um `verify()` com bcrypt cost 12. Cada operação bcrypt cost 12 em hardware de notebook fica entre 250ms e 500ms. Você mediu isso na prática: o primeiro login demorou perceptivelmente.

Em uma demonstração ao vivo, se você logar, deslogar, mostrar erro de senha e logar de novo em sequência rápida, cada operação soma. Não trava de fato, mas a percepção de lentidão diante da banca é ruim, e qualquer concorrência (você + alguém testando junto) degrada.

**Impacto:** Latência perceptível na apresentação. Não é bug, é custo de design não calibrado para demo.

**Por que acontece:** bcrypt cost 12 é correto para produção (OWASP recomenda), mas a demo roda em localhost num notebook, sem o hardware de um servidor.

**Plano de correção (Sprint 3, antes de tudo):**
- Tornar o cost do bcrypt **configurável via Settings** (`BCRYPT_ROUNDS`, default 12).
- Em `APP_ENV=development`, usar cost 10 (≈ 4x mais rápido, ainda seguro para demo).
- Manter cost 12 em produção.
- O `deps.py` lê o cost do Settings ao instanciar `BcryptPasswordHasher`, em vez de usar o default fixo.

**Decisão a registrar:** "Cost do bcrypt é parametrizado por ambiente. Produção mantém 12 (OWASP). Desenvolvimento usa 10 para responsividade em hardware de demonstração, sem comprometer a segurança real do sistema."

---

### P0-2 — `BcryptPasswordHasher` é reinstanciado a cada request

**Arquivo:** `src/docuvector/api/deps.py`
**Local:** `provide_password_hasher()` + `provide_auth_use_case()`

**Problema:**
`provide_password_hasher()` cria um `BcryptPasswordHasher()` novo a cada requisição. O construtor monta um `CryptContext` do passlib, que tem custo de inicialização não trivial (carrega backends, valida schemes). Some isso ao timing equalizer que gera um hash novo a cada instância de `AuthUseCase` (o `_timing_equalizer_hash` é cacheado por instância, mas a instância é recriada a cada request).

Resultado: o cache do timing equalizer **nunca é reaproveitado** entre requests, porque cada request cria um novo `AuthUseCase` com `_timing_equalizer_hash = None`. Ou seja, o "lazy cache" que você implementou não funciona na prática sob o ciclo de vida do FastAPI.

**Impacto:** Cada login com email inexistente paga o hash inicial do equalizer toda vez, não só na primeira. Desperdício direto de ~300ms por request de login falho.

**Plano de correção:**
- Tornar `BcryptPasswordHasher` um singleton de processo (cachear com `@lru_cache` no provider, igual ao engine).
- O `CryptContext` é thread-safe para verify/hash, então pode ser compartilhado.
- Alternativamente, pré-computar o `_timing_equalizer_hash` uma vez no startup (lifespan) e injetar.

**Decisão a registrar:** "PasswordHasher é singleton de processo. CryptContext do passlib é thread-safe e caro de construir; reconstruí-lo por request desperdiçava CPU e anulava o cache do timing equalizer."

---

## 3. Achados P1 — Altos (segurança e correção)

### P1-1 — `find_by_email` não confia no índice por causa de normalização divergente

**Arquivo:** `src/docuvector/infrastructure/persistence/user_repository_impl.py`
**Local:** `find_by_email()`

**Problema:**
A query faz `WHERE email == email.lower().strip()`. O índice `ix_users_email` é sobre a coluna `email` crua. Se algum email foi gravado com maiúscula (o seed normaliza, mas nada no banco força isso), a busca por lowercase não encontra. Pior: não há `CITEXT` nem constraint de lowercase na coluna, apesar de a extensão `citext` estar instalada no `init.sql`.

**Impacto:** Risco de inconsistência: dois usuários `User@x.com` e `user@x.com` podem coexistir, e o login fica não determinístico. Em segurança, isso é um vetor de bypass de unicidade.

**Plano de correção:**
- Usar o tipo `CITEXT` na coluna `email` (a extensão já está instalada).
- OU adicionar constraint `CHECK (email = lower(email))` + normalizar sempre na escrita.
- Recomendado: `CITEXT`, porque resolve no nível do banco e o índice passa a ser case-insensitive nativamente.
- Requer nova migration.

---

### P1-2 — CORS com `allow_credentials=True` e origem dinâmica

**Arquivo:** `src/docuvector/main.py`
**Local:** bloco CORS em `create_app()`

**Problema:**
`allow_credentials=True` combinado com `allow_origins` montado de string. Está OK hoje (só dev, origem fixa), mas é um padrão que, se copiado para produção com `allow_origins=["*"]`, vira falha grave (o browser bloqueia, mas indica intenção errada). Além disso, o CORS só é adicionado em `is_development`. Em produção, não há CORS algum, o que pode quebrar o front servido em outra origem.

**Impacto:** Baixo agora, mas é uma armadilha latente. Em produção real o front Jinja2 é same-origin, então CORS nem é necessário, mas isso precisa ser decisão explícita, não acidente.

**Plano de correção:**
- Documentar que o front é same-origin (Jinja2 servido pelo próprio FastAPI), logo CORS é desnecessário em produção e existe só para o caso de dev com porta diferente.
- Manter como está, mas com comentário explícito da decisão.

---

### P1-3 — `/health` não verifica o banco, mas a docstring promete que sim

**Arquivo:** `src/docuvector/api/routers/health.py`

**Problema:**
A docstring diz: "A partir da Sprint 2, passa a validar conectividade com o PostgreSQL." Mas o endpoint só retorna estado do processo. Discrepância entre documentação e comportamento.

**Impacto:** Health check que não checa dependências é um falso positivo. Um orquestrador (ou a banca) pode achar que o sistema está saudável quando o banco caiu.

**Plano de correção (Sprint 7, polish):**
- Adicionar verificação real: `SELECT 1` no Postgres com timeout curto.
- Separar `/health` (liveness, só processo) de `/health/ready` (readiness, checa banco + Chroma).
- Atualizar a docstring para refletir o comportamento real.

---

### P1-4 — Exceções de domínio levantadas no use case são capturadas duas vezes

**Arquivos:** `src/docuvector/api/routers/auth.py` + `src/docuvector/main.py`

**Problema:**
O router `auth.py` captura `AuthenticationError` em `try/except` e converte para `HTTPException`. Mas o `main.py` também registra um handler global para `AuthenticationError`. Como o router já converte para `HTTPException` antes de propagar, o handler global de `AuthenticationError` nunca dispara para o login. Há duas estratégias concorrentes para a mesma coisa.

**Impacto:** Confusão arquitetural. Funciona, mas tem código morto (o handler global) ou redundante (o try/except no router). Um revisor sênior vai perguntar qual é a estratégia oficial.

**Plano de correção:**
- Escolher UMA estratégia: ou o router converte tudo (e remove handlers globais de exceção de domínio), ou os handlers globais cuidam de tudo (e o router só chama o use case sem try/except).
- Recomendado: **handlers globais cuidam de tudo.** Routers ficam limpos, só orquestram. Menos código repetido. É o padrão de mercado em FastAPI.

---

## 4. Achados P2 — Médios (robustez)

### P2-1 — `event_metadata` tipado como não-nulo mas aceita NULL

**Arquivo:** `src/docuvector/infrastructure/persistence/models.py`
**Local:** `AuditLogModel.event_metadata`

**Problema:** `Mapped[dict[str, object]]` (não-opcional no tipo Python) mas `nullable=True` na coluna. O `append` grava `event.metadata or None`, então pode gravar NULL, contradizendo o tipo. Mypy não pega porque o mapeamento ORM mascara.

**Plano de correção:** Tipar como `Mapped[dict[str, object] | None]` e usar `default=dict` server-side, ou manter NULL e ajustar o tipo. Coerência entre tipo Python e schema SQL.

---

### P2-2 — `_to_entity` do user faz `UserRole(record.role)` redundante

**Arquivo:** `src/docuvector/infrastructure/persistence/user_repository_impl.py`

**Problema:** `record.role` já é `UserRole` (o SQLAlchemy Enum mapeia de volta para o enum Python). Chamar `UserRole(record.role)` de novo é redundante, embora inofensivo.

**Plano de correção:** Remover a conversão redundante. Cosmético, mas reduz ruído.

---

### P2-3 — Login com `client_ip` tem precedência de operador ambígua

**Arquivo:** `src/docuvector/api/routers/auth.py`
**Local:** `client_ip=client_ip or request.client.host if request.client else client_ip`

**Problema:** Essa expressão mistura `or` e ternário sem parênteses. A precedência real é `client_ip or (request.client.host if request.client else client_ip)`, que funciona, mas é difícil de ler e fácil de quebrar numa edição futura.

**Plano de correção:** Extrair para uma variável com nome claro antes da chamada, ou mover a resolução de IP inteiramente para o `get_client_ip` dependency (que já existe e deveria ser a fonte única).

---

### P2-4 — Sessão autônoma de audit abre conexão nova a cada evento

**Arquivo:** `src/docuvector/infrastructure/persistence/audit_repository_impl.py`

**Problema:** Cada `append()` abre uma sessão nova do pool, commita e fecha. Correto para garantir atomicidade independente, mas sob carga (ex.: rajada de logins falhos num ataque) consome conexões do pool rapidamente. O pool tem 5+5. Em um cenário de brute force, audit + verify competem por conexões.

**Impacto:** Baixo na demo, relevante em produção. O rate limit (10/min) já mitiga bastante.

**Plano de correção:** Aceitável manter para o escopo acadêmico. Documentar como trade-off conhecido. Em produção real, audit iria para uma fila assíncrona (ex.: escrever em log estruturado + ingestão batch), não síncrono no caminho do request.

---

### P2-5 — `find_by_id` no `me()` faz query a cada chamada do endpoint protegido

**Arquivo:** `src/docuvector/application/auth_use_case.py`
**Local:** `me()`

**Problema:** Todo acesso a rota protegida que chama `me()` faz um `SELECT` no banco para revalidar o usuário. Correto do ponto de vista de segurança (detecta usuário desativado após emissão do token), mas é uma query por request autenticado. Quando o RAG entrar, cada pergunta vai pagar essa query extra.

**Impacto:** N+1 latente quando o volume de requests autenticados crescer.

**Plano de correção:** Aceitável para o escopo. Em produção, cache de curta duração (ex.: 30s) do estado do usuário, ou confiar no token até expirar (trade-off segurança vs performance). Documentar a decisão.

---

## 5. Achados P3 — Baixos (polish)

### P3-1 — `conftest.py` ainda tem DATABASE_URL apontando para banco inexistente
**Arquivo:** `tests/conftest.py`
Já identificado na sessão. O `docuvector_test` não existe; testes usam o banco real. Corrigir a string e forçar `127.0.0.1` para evitar timeout IPv6. **Este é pré-requisito para os testes de integração rodarem rápido.**

### P3-2 — `ErrorResponse` schema declarado mas não usado
**Arquivo:** `src/docuvector/api/schemas/auth.py`
O `ErrorResponse` não é referenciado em nenhum `responses=` dos endpoints. Ou usar nos decorators para documentar o formato de erro no Swagger, ou remover.

### P3-3 — Container de migrations usa Python 3.11-slim com pip install em runtime
**Arquivo:** `docker/docker-compose.yml`
O serviço `migrations` instala alembic/psycopg/sqlalchemy a cada execução via pip. Lento e não reproduzível. Para o escopo está OK (roda raramente), mas o ideal seria uma imagem própria com deps pinadas.

---

## 6. Pontos fortes confirmados (manter)

A auditoria também valida o que está **correto e deve ser preservado**:

1. **Clean Architecture impecável.** Domínio puro, sem imports de framework. Regra de dependência respeitada em todos os 43 arquivos.
2. **Entidades frozen + slots.** `User` e `AuditEvent` imutáveis, previne escalonamento de privilégio acidental.
3. **`values_callable` nos Enum SQL.** Correção correta do bug de serialização de enum.
4. **Audit autônomo (NIST AU-2).** Decisão arquitetural sênior, bem documentada.
5. **Anti-enumeration real.** Mensagem genérica + timing equalizer (apesar do P0-2, a intenção e o design estão certos).
6. **Mass assignment defense.** `extra="forbid"` no `LoginRequest`.
7. **`UserResponse` sem `password_hash`.** Nunca vaza hash pela API.
8. **JWT com validação de segredo mínimo.** Fail-fast no construtor.
9. **Docker hardening.** `no-new-privileges`, `cap_drop: ALL`, SCRAM, porta bound em 127.0.0.1.
10. **Settings tipado com validators.** Fonte única de config, sem `os.environ` espalhado.
11. **`pool_pre_ping` + `pool_recycle`.** Resiliência a conexões mortas.
12. **Composition root isolado em `deps.py`.** Wiring concentrado, troca de implementação trivial.

---

## 7. Plano de refatoração priorizado (ordem de execução)

Sequência recomendada **antes de iniciar a Sprint 3**, do mais barato e impactante ao menos urgente:

### Fase A — Performance de login (resolve P0, ~30 min)
1. Adicionar `bcrypt_rounds` ao Settings (default 12, dev 10).
2. Tornar `BcryptPasswordHasher` singleton via `@lru_cache` no provider.
3. Pré-computar o timing equalizer hash uma vez (no singleton).
4. Validar: login com email inexistente deve cair de ~600ms para ~150ms em dev.

### Fase B — Correção de conftest (resolve P3-1, ~10 min)
5. Corrigir `DATABASE_URL` do conftest para o banco real.
6. Forçar `127.0.0.1` para eliminar timeout IPv6.
7. Validar: `just test-integration` roda em segundos, não minutos.

### Fase C — Consolidar tratamento de erro (resolve P1-4, ~20 min)
8. Decidir: handlers globais cuidam de tudo.
9. Remover try/except redundante dos routers.
10. Validar: login falho ainda retorna 401 com corpo correto.

### Fase D — Email case-insensitive (resolve P1-1, ~20 min)
11. Migration trocando `email` para `CITEXT`.
12. Validar: `User@x.com` e `user@x.com` colidem na unicidade.

### Fase E — Polish (resolve P1-3, P2-x, P3-x, ~30 min, pode ir para Sprint 7)
13. `/health/ready` com check de banco.
14. Ajustar tipo de `event_metadata`.
15. Remover conversão redundante em `_to_entity`.
16. Extrair resolução de `client_ip` para o dependency.
17. Usar ou remover `ErrorResponse`.

**Tempo total estimado das Fases A-D (as que importam antes da Sprint 3): ~80 minutos.**

---

## 8. Recomendação final

**Execute as Fases A e B antes de qualquer linha da Sprint 3.** São as que protegem a apresentação: login rápido e testes rápidos. As Fases C e D são higiene arquitetural que vale fazer no mesmo PR. A Fase E pode ser empurrada para a Sprint 7 (polish), exceto o `/health` se a banca for verificar.

O código está em ótimo estado para um trabalho de graduação. Os achados P0 não são defeitos de design, são calibrações de ambiente: o sistema foi desenhado para produção (cost 12, audit síncrono autônomo, revalidação por request) e precisa de pequenos ajustes para rodar liso numa demo local. Isso, inclusive, é uma boa história para a banca: "o sistema está calibrado para produção; para a demonstração, parametrizei o custo de hashing por ambiente, mantendo o rigor de segurança onde importa."

---

## 9. Tabela-resumo dos achados

| ID | Severidade | Arquivo | Problema | Fase |
|---|---|---|---|---|
| P0-1 | Crítico | auth_use_case.py | bcrypt cost 12 dobrado no login | A |
| P0-2 | Crítico | deps.py | Hasher recriado por request, cache do equalizer inútil | A |
| P1-1 | Alto | user_repository_impl.py | Email sem case-insensitive real | D |
| P1-2 | Alto | main.py | CORS só em dev, padrão arriscado | E |
| P1-3 | Alto | health.py | Health não checa banco, docstring mente | E |
| P1-4 | Alto | auth.py + main.py | Tratamento de erro duplicado | C |
| P2-1 | Médio | models.py | event_metadata tipo vs nullable | E |
| P2-2 | Médio | user_repository_impl.py | UserRole() redundante | E |
| P2-3 | Médio | auth.py | Precedência ambígua no client_ip | E |
| P2-4 | Médio | audit_repository_impl.py | Sessão nova por evento de audit | (aceito) |
| P2-5 | Médio | auth_use_case.py | Query por request no me() | (aceito) |
| P3-1 | Baixo | conftest.py | DATABASE_URL banco inexistente | B |
| P3-2 | Baixo | schemas/auth.py | ErrorResponse não usado | E |
| P3-3 | Baixo | docker-compose.yml | Migrations com pip install runtime | (aceito) |

---

**Fim da auditoria.**
