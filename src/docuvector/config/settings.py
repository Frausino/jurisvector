"""Configurações da aplicação validadas a partir do arquivo .env.

Centraliza todo acesso a variáveis de ambiente em um único ponto tipado.
Nenhum outro módulo deve ler `os.environ` diretamente.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationEnvironment(str, Enum):
    """Ambientes de execução suportados."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Configurações tipadas, lidas do `.env` e validadas no carregamento."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =============================================================
    # Aplicação
    # =============================================================
    app_env: ApplicationEnvironment = Field(
        default=ApplicationEnvironment.DEVELOPMENT,
        alias="APP_ENV",
    )
    app_name: str = Field(default="DocuVector Lite", alias="APP_NAME")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, ge=1, le=65535, alias="APP_PORT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    # =============================================================
    # PostgreSQL
    # =============================================================
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, ge=1, le=65535, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="docuvector", alias="POSTGRES_DB")
    postgres_user: str = Field(default="docuvector_app", alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(min_length=8, alias="POSTGRES_PASSWORD")
    database_url: str = Field(alias="DATABASE_URL")

    # =============================================================
    # ChromaDB
    # =============================================================
    chroma_persist_dir: Path = Field(
        default=Path("./data/chroma"),
        alias="CHROMA_PERSIST_DIR",
    )

    # =============================================================
    # JWT
    # =============================================================
    jwt_secret_key: SecretStr = Field(
        min_length=32,
        alias="JWT_SECRET_KEY",
        description=(
            "Segredo HMAC. Gerar com `python -c 'import secrets; print(secrets.token_hex(32))'`"
        ),
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256",
        alias="JWT_ALGORITHM",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,
        alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # =============================================================
    # Seed de usuários
    # =============================================================
    seed_admin_email: str = Field(alias="SEED_ADMIN_EMAIL")
    seed_admin_password: SecretStr = Field(min_length=8, alias="SEED_ADMIN_PASSWORD")
    seed_user1_email: str = Field(alias="SEED_USER1_EMAIL")
    seed_user1_password: SecretStr = Field(min_length=8, alias="SEED_USER1_PASSWORD")
    seed_user2_email: str = Field(alias="SEED_USER2_EMAIL")
    seed_user2_password: SecretStr = Field(min_length=8, alias="SEED_USER2_PASSWORD")

    # =============================================================
    # Embedder OpenAI
    # =============================================================
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
    )
    openai_embedding_dimensions: int = Field(
        default=1536,
        ge=1,
        alias="OPENAI_EMBEDDING_DIMENSIONS",
    )
    openai_embedding_cost_per_million_tokens: float = Field(
        default=0.02,
        ge=0.0,
        alias="OPENAI_EMBEDDING_COST_PER_MILLION_TOKENS",
    )

    # =============================================================
    # Embedder local (Sentence Transformers / E5)
    # =============================================================
    sentence_transformers_model: str = Field(
        default="intfloat/multilingual-e5-small",
        alias="SENTENCE_TRANSFORMERS_MODEL",
    )
    sentence_transformers_dimensions: int = Field(
        default=384,
        ge=1,
        alias="SENTENCE_TRANSFORMERS_DIMENSIONS",
    )
    hf_home: Path = Field(default=Path("./data/hf_cache"), alias="HF_HOME")

    # =============================================================
    # LLM
    # =============================================================
    openai_llm_model: str = Field(default="gpt-4o-mini", alias="OPENAI_LLM_MODEL")
    openai_llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        alias="OPENAI_LLM_TEMPERATURE",
    )
    openai_llm_max_tokens: int = Field(default=600, ge=1, alias="OPENAI_LLM_MAX_TOKENS")

    # =============================================================
    # RAG
    # =============================================================
    rag_chunk_size: int = Field(default=1000, ge=100, le=8000, alias="RAG_CHUNK_SIZE")
    rag_chunk_overlap: int = Field(default=200, ge=0, alias="RAG_CHUNK_OVERLAP")
    rag_top_k: int = Field(default=5, ge=1, le=50, alias="RAG_TOP_K")
    rag_similarity_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        alias="RAG_SIMILARITY_THRESHOLD",
    )

    # =============================================================
    # Limites operacionais
    # =============================================================
    upload_max_bytes: int = Field(default=10_485_760, ge=1, alias="UPLOAD_MAX_BYTES")
    login_rate_limit_per_minute: int = Field(
        default=10,
        ge=1,
        alias="LOGIN_RATE_LIMIT_PER_MINUTE",
    )

    # =============================================================
    # Validators
    # =============================================================
    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_application_environment_aliases(cls, candidate_value: object) -> object:
        """Aceita aliases comuns para o ambiente de execução.

        Reduz fricção operacional: muitos desenvolvedores escrevem `testing`
        (Django/Rails-like) ou `dev`/`prod` no .env. Normalizamos para os
        valores canônicos do enum antes da validação.
        """
        if not isinstance(candidate_value, str):
            return candidate_value

        aliases_to_canonical = {
            "dev": "development",
            "develop": "development",
            "testing": "test",
            "tests": "test",
            "prod": "production",
            "prd": "production",
        }
        normalized = candidate_value.strip().lower()
        return aliases_to_canonical.get(normalized, normalized)

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_psycopg(cls, candidate_url: str) -> str:
        """Garante que o driver SQLAlchemy seja o `psycopg` v3."""
        if not candidate_url.startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL deve usar o driver 'postgresql+psycopg://' (psycopg v3). "
                "Exemplo: postgresql+psycopg://user:pass@host:5432/db",  # pragma: allowlist secret
            )
        return candidate_url

    @model_validator(mode="after")
    def chunk_overlap_must_be_less_than_chunk_size(self) -> Settings:
        """RGN-06: o overlap entre chunks deve ser estritamente menor que o tamanho do chunk."""
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError(
                f"RAG_CHUNK_OVERLAP ({self.rag_chunk_overlap}) deve ser menor que "
                f"RAG_CHUNK_SIZE ({self.rag_chunk_size}).",
            )
        return self

    # =============================================================
    # Propriedades derivadas
    # =============================================================
    @property
    def is_development(self) -> bool:
        return self.app_env is ApplicationEnvironment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.app_env is ApplicationEnvironment.PRODUCTION

    @property
    def is_test(self) -> bool:
        return self.app_env is ApplicationEnvironment.TEST


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a instância singleton de Settings.

    Usar exclusivamente esta função para acessar configurações em toda
    a aplicação. O cache garante uma única leitura do `.env` por processo.
    """
    return Settings()
