"""Configurações da aplicação validadas a partir do arquivo .env."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from docuvector.domain.enums import LlmProviderName


class ApplicationEnvironment(str, Enum):
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
    # Bootstrap administrativo
    # =============================================================
    seed_admin_email: str = Field(alias="SEED_ADMIN_EMAIL")
    seed_admin_password: SecretStr = Field(min_length=12, alias="SEED_ADMIN_PASSWORD")

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

    # Provedor LLM padrão quando o request não especifica `llm_provider`.
    # Em dev/test, `mock` permite executar a suíte sem rede e sem chave.
    # Em produção local, `ollama` é o caminho operacional sem custo.
    llm_default_provider: LlmProviderName = Field(
        default=LlmProviderName.MOCK,
        alias="LLM_DEFAULT_PROVIDER",
    )

    # =============================================================
    # Ollama (LLM local via HTTP)
    # =============================================================
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
    )
    ollama_model: str = Field(
        default="qwen2.5:7b",
        alias="OLLAMA_MODEL",
        description=(
            "Modelo Ollama (ex.: 'qwen2.5:7b', 'llama3.2:3b'). "
            "Precisa ter sido baixado via `ollama pull <modelo>`."
        ),
    )
    ollama_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=600.0,
        alias="OLLAMA_TIMEOUT_SECONDS",
    )

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
    register_rate_limit_per_minute: int = Field(
        default=5,
        ge=1,
        alias="REGISTER_RATE_LIMIT_PER_MINUTE",
        description="Limite de tentativas de auto-cadastro por IP/minuto.",
    )

    # Taxa de câmbio USD → BRL usada no dashboard de KPIs.
    # Atualizável via variável de ambiente sem redeploy.
    usd_to_brl_rate: float = Field(
        default=5.70,
        ge=0.01,
        alias="USD_TO_BRL_RATE",
        description="Taxa de câmbio USD/BRL para estimativas de custo no dashboard.",
    )

    # Piso de latência mínima do POST /register (em segundos). Precisa
    # ser MAIOR que o tempo de um bcrypt no cost de produção para o
    # timing equalizer fazer efeito.
    register_min_latency_seconds: float = Field(
        default=0.6,
        ge=0.0,
        le=5.0,
        alias="REGISTER_MIN_LATENCY_SECONDS",
        description=(
            "Piso de latência do /register para anti-enumeração. Deve ser "
            ">= ao tempo de 1 bcrypt no cost de produção (~250-400ms)."
        ),
    )

    # =============================================================
    # Política de senha (NIST SP 800-63B)
    # =============================================================
    password_min_length: int = Field(
        default=12,
        ge=8,
        le=128,
        alias="PASSWORD_MIN_LENGTH",
        description="Comprimento mínimo da senha (NIST SP 800-63B).",
    )

    # =============================================================
    # Hashing de senha
    # =============================================================
    bcrypt_rounds: int | None = Field(
        default=None,
        ge=4,
        le=16,
        alias="BCRYPT_ROUNDS",
        description=(
            "Cost factor do bcrypt. Se não definido, usa 12 em produção "
            "e 10 em desenvolvimento/teste."
        ),
    )

    # =============================================================
    # Rede / proxies confiáveis
    # =============================================================
    # Lista CSV de IPs que podem fornecer X-Forwarded-For / X-Real-IP.
    # Quando a requisição NÃO vem desses peers, esses headers são
    # ignorados e o IP usado é o peer TCP direto. Defesa contra header
    # spoofing por clientes externos.
    trusted_proxy_ips: str = Field(
        default="",
        alias="TRUSTED_PROXY_IPS",
        description=(
            "Lista CSV de IPs de proxies confiáveis "
            "(ex.: '10.0.0.1,10.0.0.2'). "
            "Vazia em dev/local; preencher em produção atrás de reverse proxy."
        ),
    )

    # =============================================================
    # Validators
    # =============================================================
    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_application_environment_aliases(cls, candidate_value: object) -> object:
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
        if not candidate_url.startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL deve usar o driver 'postgresql+psycopg://' (psycopg v3). "
                "Exemplo: postgresql+psycopg://user:pass@host:5432/db",  # pragma: allowlist secret
            )
        return candidate_url

    @model_validator(mode="after")
    def chunk_overlap_must_be_less_than_chunk_size(self) -> Settings:
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
    def jwt_secret(self) -> str:
        """Retorna o segredo JWT como string pura.

        Mantém o armazenamento interno como SecretStr e evita que
        consumidores precisem conhecer a API do Pydantic.
        """
        return self.jwt_secret_key.get_secret_value()

    @property
    def effective_bcrypt_rounds(self) -> int:
        if self.bcrypt_rounds is not None:
            return self.bcrypt_rounds
        return 12 if self.is_production else 10

    @property
    def trusted_proxy_ip_set(self) -> frozenset[str]:
        """Conjunto normalizado de IPs confiáveis, sem espaços ou vazios."""
        if not self.trusted_proxy_ips:
            return frozenset()
        return frozenset(
            entry.strip() for entry in self.trusted_proxy_ips.split(",") if entry.strip()
        )

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
    return Settings()
