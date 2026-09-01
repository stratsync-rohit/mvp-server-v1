import logging

import httpx

from app.exceptions import SlackWebhookError, SlackWebhookTimeoutError

logger = logging.getLogger(__name__)


class SlackWebhookService:
    def __init__(self, timeout: float = 10):
        self.timeout = timeout

    async def send_test_message(self, webhook_url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    webhook_url,
                    json={"text": "StratSync Slack integration test successful."},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("slack_test_failed error_code=slack_timeout")
            raise SlackWebhookTimeoutError("Slack webhook timed out") from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "slack_test_failed error_code=slack_http_error http_status=%s",
                exc.response.status_code,
            )
            raise SlackWebhookError("Slack rejected the test notification") from exc
        except httpx.RequestError as exc:
            logger.error("slack_test_failed error_code=slack_connection_error")
            raise SlackWebhookError("Unable to connect to Slack") from exc

        if response.text.strip().lower() != "ok":
            logger.error("slack_test_failed error_code=slack_invalid_response")
            raise SlackWebhookError("Slack returned an unexpected response")
