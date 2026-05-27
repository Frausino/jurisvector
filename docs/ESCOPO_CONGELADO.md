# Escopo Congelado — DocuVector Lite

| Campo | Valor |
|---|---|
| Projeto | DocuVector Lite |
| Versão do escopo | 1.0 |
| Data de congelamento | 25 de maio de 2026 |
| Responsável | Davi Rosa F. |
| Disciplina | Desenvolvimento de Sistemas |
| Instituição | CEUB |
| Status | CONGELADO |

> Este documento define o que será entregue e o que não será entregue na versão 1.0 do produto. Qualquer mudança após o congelamento exige decisão formal registrada em adendo no final deste arquivo.

---

## 1. Declaração de propósito

DocuVector Lite é um portal web que permite a usuários autenticados enviar documentos textuais, indexá-los como embeddings vetoriais e consultá-los por linguagem natural, com demonstração observável de compressão de embeddings (PCA, Random Projection, Int8, Binary) e comparação cronometrada entre provedores de embedding remoto (OpenAI) e local (Sentence Transformers).

A versão 1.0 prioriza demonstrabilidade visual do trade-off entre custo, latência, espaço e fidelidade semântica, e atendimento integral dos requisitos da disciplina.

## 2. Dentro do escopo (v1.0)

1. Autenticação com login, logout, hash de senha via bcrypt e emissão de token JWT.
2. Três papéis de acesso: administrador, usuário 1, usuário 2, todos seedados via `.env`.
3. Isolamento multi-tenant: cada usuário comum vê somente seus próprios documentos. Administrador vê todos.
4. CRUD completo de documentos: upload, listar, ler, atualizar metadados, excluir, reindexar.
5. Suporte aos formatos de entrada: PDF (com texto extraível), TXT e MD.
6. Pipeline de ingestão: extração de texto, chunking por estratégia recursiva, geração de embeddings, persistência em ChromaDB e metadados em PostgreSQL.
7. Dois provedores de embedding intercambiáveis em runtime via seleção no front: OpenAI (`text-embedding-3-small`) e Sentence Transformers (`all-MiniLM-L6-v2`).
8. Quatro algoritmos de compressão de embeddings comparáveis lado a lado: PCA, Random Projection, Quantização Int8, Quantização Binária.
9. Endpoint e tela de benchmark de compressão com métricas: dimensão original, dimensão comprimida, ratio em bytes, retenção semântica via correlação de similaridades, tempo de fit, RAM ocupada antes e depois.
10. Endpoint e tela de benchmark de embedders: mesma pergunta executada nos dois provedores, com tempo de embedding, tempo de busca, custo estimado em USD.
11. Consulta semântica: pergunta em linguagem natural retorna resposta gerada por LLM com fontes citadas (chunk + score).
12. Painel administrativo: lista global de documentos, métricas agregadas, log de auditoria.
13. Log de auditoria estruturado para ações sensíveis (login, login falho, upload, exclusão, acesso negado).
14. API REST documentada via Swagger UI gerada automaticamente pelo FastAPI.
15. Tratamento global de exceções com respostas padronizadas.
16. Front-end server-side com Jinja2, HTMX e Tailwind CDN, integrado à mesma aplicação FastAPI.
17. Banco PostgreSQL executando via Docker Compose.
18. Migrations versionadas via Alembic.
19. Suite de testes automatizados com cobertura mínima de 70% em `domain` e `application`.
20. Pipeline CI no GitHub Actions com lint (ruff), tipagem (mypy strict), testes (pytest), SAST (bandit), SCA (pip-audit), SBOM (CycloneDX) e detecção de segredos (detect-secrets).
21. Documentação completa: BRD, SRS, diagramas (UC, classes, ER, sequência), README, documento de evidências.

## 3. Fora do escopo (v1.0)

1. OCR para PDFs escaneados sem camada de texto.
2. Suporte a DOCX, XLSX, HTML, EPUB, imagens ou áudio.
3. Cadastro público de usuários via UI. Usuários são criados apenas via seed administrativo.
4. Recuperação de senha por e-mail.
5. Multi-fator de autenticação (MFA/TOTP).
6. Multi-tenant com workspaces independentes. v1.0 tem isolamento por owner, não por organização.
7. Compartilhamento de documentos entre usuários comuns.
8. Edição colaborativa em tempo real.
9. Multi-agentes LLM com orquestração tipo LangGraph. v1.0 usa Use Cases determinísticos.
10. Treinamento de modelos próprios. v1.0 usa modelos pré-treinados.
11. Compressão por Product Quantization, Matryoshka representation learning ou autoencoders treinados.
12. Deploy em produção (Kubernetes, cloud). v1.0 roda localmente via Docker Compose.
13. HTTPS/TLS terminado pela aplicação. Em produção real seria via reverse proxy, fora do escopo aqui.
14. Internacionalização. Tudo em PT-BR.
15. Acessibilidade WCAG AA completa. v1.0 mira em boa prática básica, não certificação.
16. Streaming de respostas do LLM. v1.0 entrega resposta completa.
17. Cache distribuído (Redis). v1.0 sem cache.
18. Filas de processamento assíncronas (Celery, RQ). Ingestão é síncrona no v1.0.
19. Versionamento de embeddings. Reindex sobrescreve.
20. API pública com chave de cliente. API atual exige JWT de sessão.

## 4. Premissas

1. O ambiente de desenvolvimento é Windows com Docker Desktop e Python 3.11 instalados.
2. O avaliador (professor) tem acesso ao repositório GitHub público.
3. A apresentação em sala tem duração de 10 minutos.
4. Os documentos de teste serão PDFs textuais de até 10 MB.
5. A chave da API OpenAI estará disponível no ambiente local durante a demonstração. Caso falhe, o sistema deve operar 100% offline com embedder local.
6. A apresentação pode ser feita sem internet, com fallback local pré-validado.

## 5. Restrições

1. Linguagem: Python 3.11.
2. Sistema operacional alvo do desenvolvimento: Windows. Sistema deve rodar em Linux via Docker para portabilidade do banco.
3. Banco relacional obrigatório em container Docker (requisito do professor).
4. ORM obrigatório (requisito do professor): SQLAlchemy.
5. Janela de desenvolvimento: 14 dias corridos a partir de 25/05/2026.
6. Não usar LangChain nem frameworks de RAG abstratos. Stack raw para controle total e auditabilidade.
7. Não armazenar segredos no repositório. `.env` no `.gitignore`, segredos via variável de ambiente.
8. Não publicar a API OpenAI key em prints, logs ou commits.

## 6. Critérios de congelamento

O escopo será considerado descongelado somente se:

1. O professor adicionar requisito obrigatório explícito não previsto aqui.
2. Surgir bloqueio técnico inviável dentro de uma funcionalidade do escopo, exigindo substituição equivalente.
3. O cronograma indicar atraso superior a 2 dias em qualquer sprint, exigindo corte controlado de funcionalidade não crítica.

Toda alteração após o congelamento deve ser registrada na seção de adendos abaixo, com data, motivo e impacto.

## 7. Adendos ao escopo

Nenhum adendo registrado.
