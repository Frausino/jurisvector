# BRD — Business Requirements Document

**Projeto:** DocuVector Lite
**Versão:** 1.0
**Data:** 25/05/2026
**Autor:** Davi Rosa F.
**Disciplina:** Desenvolvimento de Sistemas — CEUB

---

## 1. Identificação do documento

| Item | Valor |
|---|---|
| Nome do produto | DocuVector Lite |
| Tipo de projeto | Trabalho acadêmico avaliativo (graduação) |
| Cliente | Disciplina de Desenvolvimento de Sistemas |
| Duração | 14 dias corridos |
| Apresentação | 10 minutos em sala de aula |
| Repositório | GitHub público |

## 2. Visão executiva

Sistemas de Retrieval-Augmented Generation (RAG) tornaram-se padrão para fazer modelos de linguagem responderem sobre documentos privados. A maior parte das demonstrações didáticas, no entanto, esconde dois custos críticos do RAG real: o custo de memória dos embeddings e o custo financeiro do provedor de embedding.

DocuVector Lite é um portal web que faz o pipeline RAG funcionar de ponta a ponta (upload, indexação, consulta, resposta com fontes) e expõe esses dois custos de forma observável. O sistema permite ao usuário escolher entre embedder local e remoto, e comparar quatro algoritmos de compressão vetorial lado a lado, com métricas calculadas sobre o seu próprio documento.

O diferencial não está em inventar um algoritmo novo, mas em transformar a engenharia interna de um sistema RAG em algo observável, defensável e didático.

## 3. Contexto e problema de negócio

### 3.1 Cenário

Empresas, escolas e profissionais geram grande volume de documentos textuais. Buscar informação por palavra-chave nesse volume é falho. Sistemas RAG resolvem isso transformando documentos em embeddings vetoriais e respondendo perguntas com base em trechos relevantes recuperados por similaridade.

### 3.2 Problemas observados

| ID | Problema | Impacto |
|---|---|---|
| P-01 | Embeddings de modelos modernos ocupam de 384 a 3072 floats de 32 bits por chunk. Em corpus grandes isso vira gigabytes de RAM. | Custo de infraestrutura cresce de forma não óbvia. |
| P-02 | Embedders proprietários (OpenAI, Cohere) cobram por token. Em corpus grandes isso vira centenas de dólares. | Custo financeiro recorrente. |
| P-03 | Embedders locais existem mas exigem máquina capaz e oferecem qualidade variável. | Trade-off técnico mal compreendido. |
| P-04 | Compressão de embeddings (quantização, PCA) existe na literatura mas raramente é demonstrada com métricas visíveis sobre dados do próprio usuário. | Decisões arquiteturais ficam baseadas em intuição. |
| P-05 | Sistemas RAG didáticos costumam ser scripts CLI, sem auth, sem persistência relacional, sem isolamento de dados. | Não refletem requisitos reais de software. |

### 3.3 Oportunidade

Construir um sistema didático que resolva os cinco problemas acima e ainda atenda integralmente aos requisitos de um trabalho final de disciplina de engenharia de software.

## 4. Objetivos de negócio

| ID | Objetivo | Métrica de validação |
|---|---|---|
| OBJ-01 | Demonstrar pipeline RAG completo (ingest, retrieve, answer) | Usuário consegue perguntar a um PDF e receber resposta com fontes em até 10 segundos |
| OBJ-02 | Tornar visíveis as métricas de compressão de embeddings | Tela de benchmark exibe os 4 métodos com ratio, retenção e RAM medida |
| OBJ-03 | Provar viabilidade de alternar entre embedder local e remoto | Front-end permite trocar provider e exibe tempo cronometrado de cada um |
| OBJ-04 | Entregar autenticação segura e isolamento multi-tenant | User1 não acessa documentos de User2; admin acessa todos |
| OBJ-05 | Atingir excelência técnica perceptível na apresentação | Pipeline CI verde, suite de testes, SBOM, Swagger funcional |
| OBJ-06 | Cumprir integralmente os requisitos da disciplina | Checklist do edital 100% atendido |

## 5. KPIs e critérios de aceitação

| KPI | Meta | Como medir |
|---|---|---|
| Cobertura de testes em `domain` e `application` | ≥ 70% | `pytest --cov` no CI |
| Tempo médio de resposta a uma query | < 3s (p95) com embedder local | Cronômetro no payload de retorno |
| Compressão demonstrável | Pelo menos 1 método com ratio ≥ 4x e retenção ≥ 80% | Tabela do benchmark |
| Tempo de subida do ambiente | < 60s (`docker compose up` + `alembic upgrade head`) | Cronômetro manual |
| Pipeline CI | 100% verde nas 6 fases (lint, type, test, SAST, SCA, SBOM) | GitHub Actions |
| Falhas de autorização entre usuários | 0 | Teste automatizado de isolamento |
| Vulnerabilidades CRITICAL em deps | 0 | `pip-audit` |
| Findings HIGH em SAST | 0 | `bandit` |

## 6. Stakeholders e personas

### 6.1 Stakeholders

| Stakeholder | Papel | Interesse |
|---|---|---|
| Professor da disciplina | Avaliador | Verificar atendimento dos requisitos do edital e qualidade técnica |
| Turma | Audiência da apresentação | Compreender o produto em poucos minutos |
| Davi Rosa F. | Autor e desenvolvedor | Entregar produto sólido, defender em sala, gerar artefato de portfólio |

### 6.2 Personas

**Persona A — Administrador.**
Tem visão completa do sistema. Cria e remove usuários (via seed administrativo no v1.0). Visualiza todos os documentos, todas as queries e todos os logs de auditoria. Demonstra à banca a capacidade de governança.

**Persona B — Usuário comum.**
Faz login, envia seus próprios documentos, escolhe embedder e método de compressão, faz perguntas em linguagem natural, recebe respostas com fontes citadas. Não vê documentos de outros usuários. Não acessa o painel de auditoria.

## 7. Requisitos de negócio (alto nível)

| ID | Requisito de negócio | Origem |
|---|---|---|
| RN-01 | O sistema deve exigir autenticação para qualquer ação além da tela de login | Edital |
| RN-02 | Senhas devem ser armazenadas de forma irreversível (hash com salt) | Boa prática (OWASP) |
| RN-03 | Usuários comuns devem visualizar exclusivamente seus próprios documentos | Decisão de produto |
| RN-04 | O administrador deve visualizar todos os documentos e logs | Decisão de produto |
| RN-05 | O sistema deve permitir CRUD completo de documentos | Edital |
| RN-06 | O sistema deve aceitar PDF, TXT e MD como entrada | Decisão de escopo |
| RN-07 | O sistema deve gerar embeddings de cada documento | Diferencial |
| RN-08 | O sistema deve permitir consulta por linguagem natural | Diferencial |
| RN-09 | O sistema deve oferecer pelo menos dois provedores de embedding intercambiáveis | Diferencial |
| RN-10 | O sistema deve oferecer pelo menos quatro métodos de compressão comparáveis | Diferencial |
| RN-11 | O sistema deve registrar log de auditoria de ações sensíveis | Boa prática |
| RN-12 | O sistema deve documentar sua API por Swagger | Edital |
| RN-13 | O sistema deve usar banco relacional em Docker | Edital |
| RN-14 | O sistema deve usar ORM | Edital |
| RN-15 | O sistema deve ter pelo menos 5 testes automatizados | Edital |
| RN-16 | O sistema deve fornecer tratamento elegante de erros | Edital |
| RN-17 | O sistema deve seguir arquitetura limpa e Clean Code | Edital |

## 8. Regras de negócio (RGN)

| ID | Regra | Justificativa |
|---|---|---|
| RGN-01 | Senha de usuário deve ter no mínimo 8 caracteres | Mitigação de força bruta |
| RGN-02 | Hash de senha usa bcrypt com cost factor 12 | Padrão OWASP 2026 |
| RGN-03 | Token JWT expira em 60 minutos | Limitar janela de roubo de token |
| RGN-04 | Documento pode ter no máximo 10 MB | Restringir custo de ingestão |
| RGN-05 | PDF sem texto extraível deve ser rejeitado com mensagem clara | Não suportamos OCR no v1.0 |
| RGN-06 | Chunk de texto tem tamanho alvo de 1000 caracteres com overlap de 200 | Trade-off contexto vs custo |
| RGN-07 | Top-k de recuperação é 5 chunks | Padrão didático |
| RGN-08 | Score de similaridade mínimo para retorno é 0.6 (cosine), configurável por query | Filtrar ruído com precisão prioritária |
| RGN-09 | Reindexação cria nova versão de embeddings e descarta a anterior | Manter consistência |
| RGN-10 | Acesso negado a recurso de outro usuário retorna HTTP 404 ao cliente e registra `status=forbidden` no audit log | Princípio de menor informação (OWASP) com rastreabilidade de operação |
| RGN-11 | Usuário comum não pode alterar campos `owner_id`, `role`, `status` via API | Mass assignment defense |
| RGN-12 | Cada login bem-sucedido gera evento de auditoria; cada login falho também | Detecção de tentativa |
| RGN-13 | Documentos excluídos removem também seus embeddings em ChromaDB | Princípio de consistência e LGPD |

## 9. Premissas

1. O professor avaliará via repositório GitHub e apresentação presencial.
2. A nota considera atendimento aos requisitos, qualidade técnica e criatividade.
3. O ambiente de demonstração é Windows com Docker Desktop instalado.
4. A chave OpenAI está disponível mas o sistema funciona sem ela.
5. Não há orçamento monetário; custos OpenAI são cobertos pelo autor em montante mínimo.

## 10. Restrições

1. Stack obrigatória pelo edital: backend com API REST, login, CRUD, Swagger, ORM, banco em Docker, testes.
2. Restrição autoimposta: Python 3.11 (alinhado a outros projetos do autor).
3. Restrição autoimposta: sem LangChain, sem framework RAG.
4. Restrição autoimposta: front server-side (Jinja2 + HTMX), sem build npm.
5. Janela de tempo: 14 dias.

## 11. Riscos e mitigações

| ID | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| RIS-01 | Falha de internet na apresentação | Média | Alto | Demo opera 100% local com embedder Sentence Transformers; vídeo backup gravado |
| RIS-02 | Limite ou indisponibilidade da OpenAI API | Média | Médio | Alternância em runtime para embedder local |
| RIS-03 | Estourar prazo no front-end | Média | Alto | Front entra na Sprint 5; se atrasar, demo usa Swagger UI no CRUD e Jinja2 apenas para login + benchmark |
| RIS-04 | ChromaDB conflito de versão | Baixa | Médio | Pinning estrito via `uv lock` |
| RIS-05 | Compressão Binary degradar qualidade visivelmente | Baixa | Baixo | Métrica de retenção explicita o trade-off; é feature, não bug |
| RIS-06 | Vazamento acidental de chave OpenAI no commit | Baixa | Alto | `detect-secrets` no pre-commit; `.env` no `.gitignore` |
| RIS-07 | Postgres não subir no Windows do avaliador | Baixa | Médio | Docker Compose pinned; README com troubleshooting |
| RIS-08 | Bug crítico próximo à entrega | Média | Alto | CI obrigatório verde antes de cada merge; freeze de features na Sprint 7 |

## 12. Critérios de sucesso

O projeto é considerado bem-sucedido se cumprir todos os critérios abaixo:

1. Atende 100% dos requisitos obrigatórios do edital.
2. O sistema sobe via `docker compose up` e `uv run uvicorn ...` em ambiente Windows limpo.
3. A apresentação de 10 minutos é executada sem falha técnica.
4. A banca consegue visualizar a tela de benchmark de compressão com os 4 métodos.
5. A banca consegue visualizar isolamento entre user1, user2 e admin.
6. Pipeline CI fica verde no último commit.
7. README permite a um terceiro reproduzir o ambiente em menos de 15 minutos.
8. Documento de evidências possui pelo menos 15 prints organizados.

## 13. Glossário

| Termo | Definição |
|---|---|
| Embedding | Representação vetorial de um trecho de texto em espaço numérico de alta dimensão, gerada por modelo de linguagem |
| Chunk | Trecho de texto resultante da segmentação de um documento original |
| RAG | Retrieval-Augmented Generation. Técnica que combina recuperação de trechos relevantes com geração via LLM |
| Compressão de embeddings | Técnica para reduzir o tamanho em bytes ou a dimensionalidade dos vetores, preservando ao máximo a similaridade semântica |
| PCA | Principal Component Analysis. Projeção linear que preserva variância |
| Random Projection | Projeção aleatória baseada no Lemma de Johnson-Lindenstrauss |
| Quantização Int8 | Mapeamento de float32 para inteiros de 8 bits, reduzindo 4x o tamanho |
| Quantização Binária | Mapeamento de float32 para 1 bit por dimensão (sinal), reduzindo 32x o tamanho |
| Retenção semântica | Métrica de quanto a similaridade entre pares de chunks é preservada após compressão (correlação de Pearson) |
| JWT | JSON Web Token. Padrão de token de autenticação assinado |
| OWASP | Open Web Application Security Project. Referência de segurança em aplicações |
| SBOM | Software Bill of Materials. Lista formal de dependências |
| SAST | Static Application Security Testing |
| SCA | Software Composition Analysis |
| Multi-tenant | Modelo onde múltiplos usuários compartilham a mesma instância com isolamento de dados |
