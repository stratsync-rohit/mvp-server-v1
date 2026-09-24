

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
    app_name: str = Field(
        default="MVP v1 (expandable)",
        alias="APP_NAME",
    )

    app_env: str = Field(
        default="development",
        alias="APP_ENV",
    )

    host: str = Field(
        default="0.0.0.0",
        alias="HOST",
    )

    port: int = Field(
        default=8000,
        alias="PORT",
    )

    public_base_url: str = Field(
        default="http://localhost:8000",
        alias="PUBLIC_BASE_URL",
    )

    # --- MongoDB ---
    mongodb_uri: str = Field(
        default="mongodb://mongo:27017",
        alias="MONGODB_URI",
    )

    mongodb_database: str = Field(
        default="stratsync_rrm",
        alias="MONGODB_DATABASE",
    )

    # --- n8n (system-level, single value, NOT stored per client) ---
    n8n_notification_webhook_url: str | None = Field(
        default=None,
        alias="N8N_NOTIFICATION_WEBHOOK_URL",
    )

    slack_n8n_webhook_url: str | None = Field(
        default=None,
        alias="SLACK_N8N_WEBHOOK_URL",
    )

    n8n_request_timeout_seconds: float = Field(
        default=30,
        alias="N8N_REQUEST_TIMEOUT_SECONDS",
    )

    slack_request_timeout_seconds: float = Field(
        default=10,
        alias="SLACK_REQUEST_TIMEOUT_SECONDS",
    )

    # --- Slack OAuth ---
    slack_signing_secret: str | None = Field(
        default=None,
        alias="SLACK_SIGNING_SECRET",
    )

    # These are optional so the rest of the application can run when Slack
    # OAuth has not been configured yet. The OAuth service validates that they
    # are present before attempting an exchange.

    slack_client_id: str | None = Field(
        default=None,
        alias="SLACK_CLIENT_ID",
    )

    slack_client_secret: str | None = Field(
        default=None,
        alias="SLACK_CLIENT_SECRET",
    )

    slack_oauth_redirect_uri: str = Field(
        default="https://34.100.226.192.nip.io/api/slack/oauth/callback",
        alias="SLACK_OAUTH_REDIRECT_URI",
    )

    slack_oauth_scopes: str = Field(
        default="incoming-webhook,chat:write",
        alias="SLACK_OAUTH_SCOPES",
    )

    slack_oauth_success_url: str = Field(
        default="http://localhost:3000/integrations/slack/success",
        alias="SLACK_OAUTH_SUCCESS_URL",
    )

    slack_oauth_error_url: str = Field(
        default="http://localhost:3000/integrations/slack/error",
        alias="SLACK_OAUTH_ERROR_URL",
    )

    slack_oauth_state_secret: str | None = Field(
        default=None,
        alias="SLACK_OAUTH_STATE_SECRET",
    )

    slack_connection_token_encryption_key: str | None = Field(
        default=None,
        alias="SLACK_CONNECTION_TOKEN_ENCRYPTION_KEY",
    )

    # --- CORS ---
    cors_origins: str = Field(
        default=(
            "http://localhost:3000,"
            "http://localhost:5173,"
            "http://localhost:3001"
        ),
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @field_validator("n8n_request_timeout_seconds")
    @classmethod
    def _positive_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(
                "N8N_REQUEST_TIMEOUT_SECONDS must be positive"
            )
        return v

    @field_validator("slack_request_timeout_seconds")
    @classmethod
    def _positive_slack_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(
                "SLACK_REQUEST_TIMEOUT_SECONDS must be positive"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance - env is only parsed once per process."""
    return Settings()
