from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_max_input_chars: int = Field(default=8000, ge=1)
    llm_history_limit: int = Field(default=20, ge=1)
    # Empty = provider default; 0 disables thinking where the model supports it.
    llm_thinking_budget: int | None = None

    ai_max_active_generations_per_user: int = Field(default=2, ge=1)
    ai_requests_per_minute_per_user: int = Field(default=10, ge=1)
    ai_daily_message_quota: int = Field(default=50, ge=1)
    ai_daily_token_quota: int = Field(default=200_000, ge=1)
    ai_stale_generation_seconds: int = Field(default=300, ge=30)

    @field_validator(
        "llm_model_max_input_tokens",
        "llm_model_max_output_tokens",
        "llm_thinking_budget",
        "gemini_api_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        """docker compose passes unset variables as empty strings."""
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("llm_provider", "llm_default_model", "llm_allowed_models", mode="after")
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
        return self


_PLACEHOLDER_PREFIXES = ("replace_with", "replace_me", "change_me", "changeme")


@lru_cache
def get_settings() -> Settings:
    return Settings()
