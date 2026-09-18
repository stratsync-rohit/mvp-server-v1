import logging

import httpx

from app.exceptions import (
    SlackWebhookError,
    SlackWebhookTimeoutError,
)

logger = logging.getLogger(__name__)


class SlackWebhookService:
    def __init__(self, timeout: float = 10):
        self.timeout = timeout

    async def _post(
        self,
        webhook_url: str,
        payload: dict,
        operation: str,
    ) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                )

                response.raise_for_status()

        except httpx.TimeoutException as exc:
            logger.error(
                "slack_%s_failed error_code=slack_timeout",
                operation,
            )

            raise SlackWebhookTimeoutError(
                "Slack webhook timed out"
            ) from exc

        except httpx.HTTPStatusError as exc:
            logger.error(
                "slack_%s_failed "
                "error_code=slack_http_error "
                "http_status=%s",
                operation,
                exc.response.status_code,
            )

            raise SlackWebhookError(
                "Slack rejected the notification"
            ) from exc

        except httpx.RequestError as exc:
            logger.error(
                "slack_%s_failed "
                "error_code=slack_connection_error",
                operation,
            )

            raise SlackWebhookError(
                "Unable to connect to Slack"
            ) from exc

        if response.text.strip().lower() != "ok":
            logger.error(
                "slack_%s_failed "
                "error_code=slack_invalid_response "
                "response=%s",
                operation,
                response.text[:200],
            )

            raise SlackWebhookError(
                "Slack returned an unexpected response"
            )

    async def send(
        self,
        webhook_url: str,
        payload: dict,
    ) -> None:
        """
        Send a rendered Slack Block Kit payload directly
        to a Slack Incoming Webhook.
        """

        await self._post(
            webhook_url=webhook_url,
            payload=payload,
            operation="notification",
        )

    async def send_test_message(
        self,
        webhook_url: str,
    ) -> None:
        """
        Send a simple Slack integration test message.
        """

        await self._post(
            webhook_url=webhook_url,
            payload={
                "text": (
                    "StratSync Slack integration "
                    "test successful."
                )
            },
            operation="test",
        )