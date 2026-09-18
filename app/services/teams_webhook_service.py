from __future__ import annotations

from typing import Any

import httpx


class TeamsWebhookError(Exception):
    """Raised when a Microsoft Teams webhook request fails."""


class TeamsWebhookService:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def send(
        self,
        webhook_url: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Send a rendered Adaptive Card payload directly to a
        Microsoft Teams / Power Automate webhook.

        The webhook URL must remain server-side and must never
        be returned or included in exception messages.
        """

        if not webhook_url or not webhook_url.strip():
            raise TeamsWebhookError(
                "Teams webhook URL is missing."
            )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds
            ) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                )

                response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise TeamsWebhookError(
                "Teams webhook request timed out."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise TeamsWebhookError(
                "Teams webhook returned a non-success response."
            ) from exc

        except httpx.RequestError as exc:
            raise TeamsWebhookError(
                "Unable to reach Teams webhook."
            ) from exc