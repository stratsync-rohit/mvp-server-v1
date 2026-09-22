import logging
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.exceptions import (
    SlackOAuthConfigurationError,
    SlackOAuthConnectionError,
    SlackOAuthResponseError,
    SlackOAuthTimeoutError,
)
from app.schemas.slack_workspace_installation import (
    SlackIncomingWebhookMetadata,
    SlackWorkspaceInstallation,
)


logger = logging.getLogger(__name__)


def _optional_string(value):
    return value if isinstance(value, str) else None


class SlackOAuthService:
    TOKEN_EXCHANGE_URL = "https://slack.com/api/oauth.v2.access"
    AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"

    def __init__(self, settings: Settings):
        self.settings = settings

    def build_authorization_url(self, state: str) -> str:
        if not self.settings.slack_client_id:
            logger.error(
                "slack_oauth_start_failed error_code=configuration_missing"
            )
            raise SlackOAuthConfigurationError(
                "Slack OAuth is not configured"
            )

        query = urlencode(
            {
                "client_id": self.settings.slack_client_id,
                "scope": self.settings.slack_oauth_scopes,
                "redirect_uri": self.settings.slack_oauth_redirect_uri,
                "state": state,
            }
        )
        return f"{self.AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str) -> SlackWorkspaceInstallation:
        if not code or not code.strip():
            raise SlackOAuthResponseError("Slack OAuth code is required")

        if not self.settings.slack_client_id or not self.settings.slack_client_secret:
            logger.error("slack_oauth_exchange_failed error_code=configuration_missing")
            raise SlackOAuthConfigurationError(
                "Slack OAuth is not configured"
            )

        form_data = {
            "client_id": self.settings.slack_client_id,
            "client_secret": self.settings.slack_client_secret,
            "code": code,
            "redirect_uri": self.settings.slack_oauth_redirect_uri,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.slack_request_timeout_seconds
            ) as client:
                response = await client.post(
                    self.TOKEN_EXCHANGE_URL,
                    data=form_data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("slack_oauth_exchange_failed error_code=timeout")
            raise SlackOAuthTimeoutError(
                "Slack OAuth exchange timed out"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "slack_oauth_exchange_failed error_code=http_status"
            )
            raise SlackOAuthResponseError(
                "Slack OAuth exchange failed"
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "slack_oauth_exchange_failed error_code=connection"
            )
            raise SlackOAuthConnectionError(
                "Unable to connect to Slack OAuth"
            ) from exc

        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            logger.error(
                "slack_oauth_exchange_failed error_code=malformed_response"
            )
            raise SlackOAuthResponseError(
                "Slack returned an invalid OAuth response"
            ) from exc

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            logger.error("slack_oauth_exchange_failed error_code=slack_rejected")
            raise SlackOAuthResponseError("Slack rejected the OAuth exchange")

        try:
            team = payload["team"]
            slack_team_id = team["id"]
            slack_team_name = team["name"]
            access_token = payload["access_token"]
            app_id = payload["app_id"]
        except (KeyError, TypeError) as exc:
            logger.error(
                "slack_oauth_exchange_failed error_code=missing_fields"
            )
            raise SlackOAuthResponseError(
                "Slack returned an incomplete OAuth response"
            ) from exc

        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                slack_team_id,
                slack_team_name,
                access_token,
                app_id,
            )
        ):
            logger.error(
                "slack_oauth_exchange_failed error_code=invalid_fields"
            )
            raise SlackOAuthResponseError(
                "Slack returned an incomplete OAuth response"
            )

        enterprise = payload.get("enterprise")
        if enterprise is not None and not isinstance(enterprise, dict):
            enterprise = None

        incoming_webhook = payload.get("incoming_webhook")
        webhook_metadata = None
        if isinstance(incoming_webhook, dict):
            webhook_metadata = SlackIncomingWebhookMetadata(
                channel=_optional_string(incoming_webhook.get("channel")),
                channel_id=_optional_string(
                    incoming_webhook.get("channel_id")
                ),
                configuration_url=_optional_string(
                    incoming_webhook.get("configuration_url")
                ),
                url=_optional_string(incoming_webhook.get("url")),
            )

        bot_user_id = payload.get("bot_user_id")
        token_type = payload.get("token_type")
        scope = payload.get("scope")
        enterprise_id = (enterprise or {}).get("id")
        if any(
            value is not None and not isinstance(value, str)
            for value in (bot_user_id, token_type, scope, enterprise_id)
        ):
            logger.error(
                "slack_oauth_exchange_failed error_code=invalid_fields"
            )
            raise SlackOAuthResponseError(
                "Slack returned an invalid OAuth response"
            )

        try:
            return SlackWorkspaceInstallation(
                slack_team_id=slack_team_id,
                slack_team_name=slack_team_name,
                enterprise_id=enterprise_id,
                app_id=app_id,
                bot_user_id=bot_user_id,
                access_token=access_token,
                token_type=token_type or "bot",
                scope=scope,
                is_enterprise_install=bool(
                    payload.get("is_enterprise_install", False)
                ),
                incoming_webhook=webhook_metadata,
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "slack_oauth_exchange_failed error_code=invalid_fields"
            )
            raise SlackOAuthResponseError(
                "Slack returned an invalid OAuth response"
            ) from exc
