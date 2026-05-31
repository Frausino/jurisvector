# Incidentes Resolvidos

## INC-001 — Dados não persistidos após registro

Causa:
Uso de flush() sem commit().

Sintoma:
Usuário era criado durante a requisição, mas login falhava.

Correção:
Garantir commit transacional via session_scope().

Aprendizado:
flush != commit.


## INC-002 — Drift entre ORM e PostgreSQL

Causa:
DocumentModel permitia NULL enquanto schema físico mantinha NOT NULL.

Sintoma:
Falha de upload com NotNullViolation.

Correção:
Migration Alembic explícita.

Aprendizado:
Schema do banco é a verdade.


## INC-003 — Dependency Override ignorado

Causa:
Teste sobrescrevia get_llm_client enquanto FastAPI consumia provide_llm_client.

Sintoma:
Stub não utilizado e OpenAI real era chamado.

Correção:
Alinhar dependency_overrides ao provider registrado.

Aprendizado:
Overrides devem apontar para o callable usado em Depends().
