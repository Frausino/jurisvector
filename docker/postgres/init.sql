-- =============================================================
-- DocuVector Lite — Inicialização do banco
-- Roda automaticamente na primeira subida do Postgres
-- (volume vazio). Coloca extensões que o Alembic não cria.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";
