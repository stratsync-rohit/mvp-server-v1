import logging

import httpx

from app.exceptions import (
    UpstreamConnectionError,
    UpstreamConfigurationError,
    UpstreamError,
    UpstreamTimeoutError
)

logger = logging.getLogger(__name__)


class N8nService:

    def __init__(self, settings):
        configured_url = settings.n8n_notification_webhook_url
        self.webhook_url = configured_url.strip() if configured_url else None
        self.timeout = settings.n8n_request_timeout_seconds

    async def trigger_notification(self, payload: dict):
        if not self.webhook_url:
            logger.error("n8n_request_failed error_code=n8n_config_missing")
            raise UpstreamConfigurationError(
                "Notification workflow is not configured"
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("n8n_request_failed error_code=n8n_timeout")
            raise UpstreamTimeoutError(
                "Notification workflow timed out"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error(
                "n8n_request_failed error_code=n8n_delivery_failed "
                "http_status=%s",
                status_code,
            )
            raise UpstreamError(
                "Unable to trigger notification workflow",
                error_code="n8n_delivery_failed",
                http_status=status_code,
            ) from exc
        except httpx.ConnectError as exc:
            logger.error(
                "n8n_request_failed error_code=n8n_connection_failed"
            )
            raise UpstreamConnectionError(
                "Unable to connect to notification workflow"
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "n8n_request_failed error_code=n8n_connection_failed"
            )
            raise UpstreamConnectionError(
                "Unable to connect to notification workflow"
            ) from exc

        if not response.content:
            return {"status": "accepted"}

        try:
            return response.json()
        except ValueError:
            return {"status": "accepted"}
