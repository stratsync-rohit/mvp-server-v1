from typing import Any

from app.services.teams_card_renderer import build_teams_notification_payload
from app.utils.payload_size import utf8_json_size_bytes


class TeamsPayloadPreviewService:
    LIMIT_BYTES = 28 * 1024

    def __init__(self, notification_service):
        self.notification_service = notification_service

    async def preview_size(self, risk: dict[str, Any]) -> dict[str, Any]:
        renderer_risk = (
            await self.notification_service.prepare_notification_risk_payload(
                risk=risk,
            )
        )
        teams_payload = build_teams_notification_payload(renderer_risk)
        size_bytes = utf8_json_size_bytes(teams_payload)

        return {
            "bytes": size_bytes,
            "kb": round(size_bytes / 1024, 2),
            "limit_bytes": self.LIMIT_BYTES,
            "limit_kb": 28,
            "too_large": size_bytes > self.LIMIT_BYTES,
            "measurement": "rendered-teams-payload",
        }
