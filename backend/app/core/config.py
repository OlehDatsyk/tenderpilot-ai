"""Application settings, loaded from environment variables (and an optional local .env file)."""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("tenderpilot.config")

AIProviderName = Literal["none", "demo", "openai", "anthropic", "gemini"]

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-5-5",
    # OpenAI / Gemini model names change often - set AI_MODEL explicitly for these providers.
    "openai": "gpt-4.1",
    "gemini": "gemini-2.5-pro",
    "demo": "demo-heuristic-v1",
    "none": "",
}


_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Real environment variables always win; .env files are a local-development convenience.
    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "TenderPilot AI"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    secret_key: str = Field(default="", description="JWT signing key (min 32 chars). Required in production.")
    database_url: str = "postgresql+psycopg://tenderpilot:tenderpilot@127.0.0.1:5435/tenderpilot"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    registration_enabled: bool = True

    # AI
    ai_provider: AIProviderName = "none"
    ai_model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ai_timeout_seconds: float = 180.0
    ai_max_retries: int = 2
    ai_max_context_chars: int = 400_000
    allow_org_ai_keys: bool = True
    encryption_key: str = Field(default="", description="Fernet key used to encrypt organisation-supplied AI keys.")

    # Storage
    storage_backend: Literal["database", "local"] = "database"
    local_storage_dir: str = "./storage"
    local_storage_is_persistent: bool = False
    max_upload_mb: int = 20

    # Rate limiting (per client IP, in-memory, per process)
    rate_limit_auth_per_minute: int = 10
    rate_limit_ai_per_minute: int = 20

    docs_enabled: bool = True
    trusted_proxy_headers: bool = False

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, value: str) -> str:
        # Render / Heroku style URLs -> SQLAlchemy psycopg3 driver.
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value[len("postgres://") :]
        elif value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.environment == "production":
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to at least 32 random characters in production.")
            if self.database_url.startswith("sqlite"):
                raise ValueError("SQLite is not supported in production; set DATABASE_URL to PostgreSQL.")
            if self.storage_backend == "local" and not self.local_storage_is_persistent:
                raise ValueError(
                    "STORAGE_BACKEND=local requires a persistent disk in production. "
                    "Use STORAGE_BACKEND=database or mount a disk and set LOCAL_STORAGE_IS_PERSISTENT=true."
                )
            if "*" in self.cors_origin_list:
                raise ValueError("Wildcard CORS origins are not allowed in production.")
        elif not self.secret_key:
            # Development convenience only: tokens become invalid on restart.
            self.secret_key = secrets.token_urlsafe(48)
            logger.warning("SECRET_KEY not set - generated an ephemeral development key.")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def env_api_key(self, provider: str) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
        }.get(provider, "")


@lru_cache
def get_settings() -> Settings:
    # The test suite sets TENDERPILOT_IGNORE_ENV_FILE so a developer's local .env never leaks into tests.
    if os.environ.get("TENDERPILOT_IGNORE_ENV_FILE"):
        return Settings(_env_file=None)  # type: ignore[call-arg]
    return Settings()
