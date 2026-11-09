from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.database.vector import EMBEDDING_COLUMN_DIMENSIONS


class AppEnv(StrEnum):
    development = "development"
    testing = "testing"
    production = "production"


class CookieSameSite(StrEnum):
    lax = "lax"
    strict = "strict"
    none = "none"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: AppEnv = AppEnv.development
    app_secret_key: str = Field(min_length=32)
    app_version: str = "0.1.0"

    # Database
    database_url: PostgresDsn
    database_migration_url: PostgresDsn
    database_test_url: PostgresDsn | None = None

    # CORS / URLs
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # Cookies
    cookie_secure: bool = False
    cookie_samesite: CookieSameSite = CookieSameSite.lax
    cookie_name: str = "aw_session"

    # Only enable behind a reverse proxy that overwrites X-Forwarded-For (rate limiting / audit IP)
    trust_proxy_headers: bool = False

    # Email
    email_provider: str = "console"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    email_from_address: str = "noreply@axonweave.app"
    email_from_name: str = "Axonweave"

    # AI (Phase 2). All optional: with no provider the app runs and AI endpoints answer 503.
    llm_provider: str = ""
    # Provider model id; verify with scripts/list_llm_models.py (D-38). Never hardcoded.
    llm_default_model: str = ""
    # Test-only: pause between FakeProvider chunks so e2e tests can press Stop.
    fake_llm_chunk_delay_seconds: float = Field(default=0.0, ge=0.0, le=2.0)
    # Optional comma-separated extra provider model ids users may select.
    llm_allowed_models: str = ""
    # Optional verified limits for the default model (unknown -> conservative defaults, D-47).
    llm_model_max_input_tokens: int | None = None
    llm_model_max_output_tokens: int | None = None
    gemini_api_key: SecretStr | None = None

    llm_connect_timeout_seconds: float = 10
    llm_generation_timeout_seconds: float = 60
    llm_stream_inactivity_timeout_seconds: float = 30
    llm_overall_timeout_seconds: float = 120
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=2000, ge=1)
    llm_fallback_input_tokens: int = Field(
        default=8000, ge=1
    )  # context budget when a model's limit is unknown
    llm_max_input_chars: int = Field(default=8000, ge=1)
    llm_history_limit: int = Field(default=20, ge=1)
    # Empty = provider default; 0 disables thinking where the model supports it.
    llm_thinking_budget: int | None = None

    ai_max_active_generations_per_user: int = Field(default=2, ge=1)
    ai_requests_per_minute_per_user: int = Field(default=10, ge=1)
    ai_daily_message_quota: int = Field(default=50, ge=1)
    ai_daily_token_quota: int = Field(default=200_000, ge=1)
    ai_stale_generation_seconds: int = Field(default=300, ge=30)

    # ── Phase 3: object storage, Redis, Celery, embeddings, limits (D-62..D-71) ──
    # Empty storage_backend = not configured: document endpoints answer 503, everything else runs.
    storage_backend: str = ""  # "s3" | "memory" (memory only in development/testing)
    storage_endpoint_url: str = ""
    storage_region: str = "us-east-1"
    storage_bucket: str = ""
    storage_access_key_id: SecretStr | None = None
    storage_secret_access_key: SecretStr | None = None
    storage_force_path_style: bool = True
    storage_server_side_encryption: str = ""

    redis_url: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_task_soft_time_limit_seconds: int = Field(default=240, ge=5)
    celery_task_hard_time_limit_seconds: int = Field(default=300, ge=10)
    celery_max_retries: int = Field(default=3, ge=0, le=10)
    # "redis" needs redis_url; "memory" is the in-process limiter (tests, single instance) (D-65).
    rate_limit_backend: str = "memory"

    embedding_provider: str = ""  # "gemini" | "fake" (fake only in development/testing)
    embedding_model: str = ""  # verify with scripts/list_embedding_models.py (D-69); never guessed
    embedding_dimensions: int = Field(default=EMBEDDING_COLUMN_DIMENSIONS, ge=1)
    embedding_index_version: int = Field(default=1, ge=1)
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_timeout_seconds: float = Field(default=30, gt=0)
    embedding_max_retries: int = Field(default=3, ge=0, le=10)
    # Retrieval (D-73). Scores are cosine similarity (0..1) for the verified model; calibrated in
    # docs/RETRIEVAL_EVALUATION.md, never guessed.
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    retrieval_candidates: int = Field(default=40, ge=5, le=200)
    retrieval_min_vector_score: float = Field(default=0.55, ge=0.0, le=1.0)
    retrieval_context_token_budget: int = Field(default=4000, ge=200)
    retrieval_rrf_k: int = Field(default=60, ge=1)
    search_requests_per_minute_per_user: int = Field(default=30, ge=1)

    doc_max_file_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    doc_max_files_per_request: int = Field(default=5, ge=1)
    doc_max_documents_per_user: int = Field(default=200, ge=1)
    doc_max_total_bytes_per_user: int = Field(default=1024**3, ge=1)
    doc_uploads_per_minute_per_user: int = Field(default=20, ge=1)
    doc_max_pages: int = Field(default=500, ge=1)
    doc_chunk_target_tokens: int = Field(default=400, ge=50)
    doc_chunk_overlap_tokens: int = Field(default=60, ge=0)
    doc_chunk_max_tokens: int = Field(default=600, ge=100)
    doc_ocr_timeout_seconds: int = Field(default=60, ge=5)
    # Optional address-space cap for a worker process in MB (0 = off). The container memory limit in
    # compose is the enforced cap; this only turns a runaway parser into a MemoryError.
    worker_memory_limit_mb: int = Field(default=0, ge=0)
    doc_max_extracted_chars: int = Field(default=2_000_000, ge=1)
    doc_zip_max_entries: int = Field(default=2000, ge=1)
    doc_zip_max_uncompressed_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    doc_zip_max_ratio: int = Field(default=100, ge=1)
    doc_image_max_pixels: int = Field(default=50_000_000, ge=1)
    doc_ocr_enabled: bool = True
    doc_ocr_dpi: int = Field(default=200, ge=72, le=400)
    doc_ocr_languages: str = "eng"
    scanner_backend: str = "none"  # "none" | "clamav" (fail-closed when clamav, D-71)

    @field_validator(
        "llm_model_max_input_tokens",
        "llm_model_max_output_tokens",
        "llm_thinking_budget",
        "gemini_api_key",
        "storage_access_key_id",
        "storage_secret_access_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        """docker compose passes unset variables as empty strings."""
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator(
        "llm_provider",
        "llm_default_model",
        "llm_allowed_models",
        "storage_backend",
        "rate_limit_backend",
        "embedding_provider",
        "embedding_model",
        "scanner_backend",
        mode="after",
    )
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("database_url", "database_migration_url", mode="before")
    @classmethod
    def _stringify_dsn(cls, v: object) -> object:
        return str(v) if v else v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        """Refuse to start in production with insecure or placeholder configuration."""
        if self.llm_provider.lower() == "fake" and self.app_env not in (
            AppEnv.development,
            AppEnv.testing,
        ):
            raise ValueError("LLM_PROVIDER=fake is only allowed in development and testing")
        non_dev = self.app_env not in (AppEnv.development, AppEnv.testing)
        if self.storage_backend.lower() == "memory" and non_dev:
            raise ValueError("STORAGE_BACKEND=memory is only allowed in development and testing")
        if self.embedding_provider.lower() == "fake" and non_dev:
            raise ValueError("EMBEDDING_PROVIDER=fake is only allowed in development and testing")
        if self.storage_backend.lower() not in ("", "s3", "memory"):
            raise ValueError("STORAGE_BACKEND must be 's3', 'memory' or empty")
        if self.rate_limit_backend.lower() not in ("memory", "redis"):
            raise ValueError("RATE_LIMIT_BACKEND must be 'memory' or 'redis'")
        if self.rate_limit_backend.lower() == "redis" and not self.redis_url:
            raise ValueError("RATE_LIMIT_BACKEND=redis needs REDIS_URL")
        if self.scanner_backend.lower() not in ("none", "clamav"):
            raise ValueError("SCANNER_BACKEND must be 'none' or 'clamav'")
        if self.celery_task_soft_time_limit_seconds >= self.celery_task_hard_time_limit_seconds:
            raise ValueError("CELERY soft time limit must be below the hard limit")
        if self.embedding_provider and self.embedding_dimensions != EMBEDDING_COLUMN_DIMENSIONS:
            raise ValueError(
                "EMBEDDING_DIMENSIONS does not match the vector column "
                f"({EMBEDDING_COLUMN_DIMENSIONS}); changing it needs a migration (D-69)"
            )
        if self.app_env != AppEnv.production:
            return self
        if self.gemini_api_key is not None and (
            self.gemini_api_key.get_secret_value().lower().startswith(_PLACEHOLDER_PREFIXES)
        ):
            raise ValueError("GEMINI_API_KEY must not be a placeholder in production")
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if self.app_secret_key.lower().startswith(_PLACEHOLDER_PREFIXES):
            raise ValueError("APP_SECRET_KEY must not be a default placeholder in production")
        if not self.frontend_url.startswith("https://"):
            raise ValueError("FRONTEND_URL must use https in production")
        for name in ("database_url", "database_migration_url"):
            if any(p in str(getattr(self, name)).lower() for p in _PLACEHOLDER_PREFIXES):
                raise ValueError(f"{name.upper()} must not contain a placeholder password")
        if self.storage_backend.lower() == "s3":
            missing = [
                n for n in ("storage_endpoint_url", "storage_bucket") if not getattr(self, n)
            ]
            if missing or not (self.storage_access_key_id and self.storage_secret_access_key):
                raise ValueError(
                    "STORAGE_* endpoint, bucket and credentials are required in production"
                )
            for secret in (self.storage_access_key_id, self.storage_secret_access_key):
                if secret.get_secret_value().lower().startswith(_PLACEHOLDER_PREFIXES):
                    raise ValueError("STORAGE_* credentials must not be placeholders in production")
                if secret.get_secret_value().startswith("axonweave_dev"):
                    raise ValueError("STORAGE_* credentials must not be the development defaults")
            if not self.storage_endpoint_url.startswith("https://"):
                raise ValueError("STORAGE_ENDPOINT_URL must use https in production")
        if self.storage_backend and not self.celery_broker_url:
            raise ValueError("CELERY_BROKER_URL is required in production when storage is enabled")
        return self


_PLACEHOLDER_PREFIXES = ("replace_with", "replace_me", "change_me", "changeme")


@lru_cache
def get_settings() -> Settings:
    return Settings()
