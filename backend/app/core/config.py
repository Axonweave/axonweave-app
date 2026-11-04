from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator, model_validator
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

    # Email
    email_provider: str = "console"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    email_from_address: str = "noreply@axonweave.app"
    email_from_name: str = "Axonweave"

    @field_validator("database_url", "database_migration_url", mode="before")
    @classmethod
    def _stringify_dsn(cls, v: object) -> object:
        return str(v) if v else v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        """Refuse to start in production with insecure or placeholder configuration."""
        if self.app_env != AppEnv.production:
            return self
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
