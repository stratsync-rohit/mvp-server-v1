"""
Application configuration.

Loads settings from environment variables (via .env in local/dev, or real
environment variables in production/Docker). Uses pydantic-settings so all
config is validated and typed in one place.
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = Field(default="MVP v1 (expandable)", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # --- MongoDB ---
    mongodb_uri: str = Field(default="mongodb://mongo:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="stratsync_rrm", alias="MONGODB_DATABASE")

    # --- n8n (system-level, single value, NOT stored per client) ---
    n8n_notification_webhook_url: str | None = Field(
        default=None,
        alias="N8N_NOTIFICATION_WEBHOOK_URL",
    )
    n8n_request_timeout_seconds: float = Field(
        default=30, alias="N8N_REQUEST_TIMEOUT_SECONDS"
    )

    # --- CORS ---
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @field_validator("n8n_request_timeout_seconds")
    @classmethod
    def _positive_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("N8N_REQUEST_TIMEOUT_SECONDS must be positive")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance - env is only parsed once per process."""
    return Settings()
