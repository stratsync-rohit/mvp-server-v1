from bson import ObjectId

from app.exceptions import (
    ConflictError,
    InactiveResourceError,
    NotFoundError,
    UpstreamConnectionError,
    UpstreamError,
    UpstreamTimeoutError
)
from app.utils.mongo_serializer import serialize_mongo_document
from app.utils.mitigation_plan import normalize_mitigation_plan_for_notification


class NotificationService:

    def __init__(
        self,
        notification_repository,
        risk_repository,
        teams_channel_repository,
        slack_destination_repository,
        client_repository,
        n8n_service,
        slack_n8n_service,
    ):
        self.notification_repository = notification_repository
        self.risk_repository = risk_repository
        self.teams_channel_repository = teams_channel_repository
        self.slack_destination_repository = slack_destination_repository
        self.client_repository = client_repository
        self.n8n_service = n8n_service
        self.slack_n8n_service = slack_n8n_service

    async def _resolve_destination(self, destination_id: str):
        if not ObjectId.is_valid(destination_id):
            raise NotFoundError("Destination not found")

        teams_destination = await self.teams_channel_repository.get_by_id(
            destination_id
        )
        if teams_destination is not None:
            return "teams", teams_destination

        slack_destination = await self.slack_destination_repository.get_by_id(
            destination_id
        )
        if slack_destination is not None:
            return "slack", slack_destination

        raise NotFoundError("Destination not found")

    async def trigger_notification(
        self,
        risk_id: str,
        destination_id: str
    ):
        platform, destination = await self._resolve_destination(
            destination_id
        )

        if not destination.get("is_active", True):
            raise InactiveResourceError(
                f"{platform.title()} destination is inactive"
            )

        risk = await self.risk_repository.get_risk_by_id(risk_id)
        if risk is None:
            raise NotFoundError("Risk not found")

        client = await self.client_repository.get_client_by_id(
            str(destination["client_id"])
        )
        if client is None:
            raise NotFoundError("Client not found")
        if not client.get("is_active", True):
            raise InactiveResourceError("Client is inactive")

        if platform == "teams":
            destination_webhook_url = destination.get("teams_webhook_url")
            if not destination_webhook_url:
                raise InactiveResourceError("Teams webhook is not configured")
        else:
            destination_webhook_url = destination.get("webhook_url")
            if not destination_webhook_url:
                raise InactiveResourceError("Slack webhook is not configured")

        guard_acquired = (
            await self.notification_repository.acquire_duplicate_guard(
                risk_id=risk_id,
                destination_id=destination_id
            )
        )
        if not guard_acquired:
            raise ConflictError(
                "Notification was already triggered recently"
            )

        notification_data = {
            "risk_id": risk_id,
            "destination_id": destination["_id"],
            "client_id": destination["client_id"],
            "team_name": destination.get("team_name") or "",
            "channel_name": destination.get("channel_name"),
            "risk_title": risk.get("title") or "",
            "severity": risk.get("severity"),
            "status": "pending"
        }
        if platform == "slack":
            notification_data["platform"] = "slack"
        notification = await self.notification_repository.create_notification(
            notification_data
        )

        risk_payload = serialize_mongo_document(risk)
        risk_payload.pop("id", None)
        risk_payload = normalize_mitigation_plan_for_notification(risk_payload)
        if platform == "teams":
            payload = {
                "teams_webhook_url": destination_webhook_url,
                "risk": risk_payload
            }
            delivery_service = self.n8n_service
        else:
            payload = {
                "platform": "slack",
                "destination_id": str(destination["_id"]),
                "client_id": str(destination["client_id"]),
                "workspace_domain": destination["workspace_domain"],
                "channel_id": destination["channel_id"],
                "channel_name": destination["channel_name"],
                "slack_webhook_url": destination_webhook_url,
                "risk": risk_payload,
            }
            delivery_service = self.slack_n8n_service

        try:
            await delivery_service.trigger_notification(payload)
        except UpstreamTimeoutError:
            await self.notification_repository.mark_failed(
                notification["_id"], "n8n_timeout"
            )
            raise
        except UpstreamConnectionError:
            await self.notification_repository.mark_failed(
                notification["_id"], "n8n_connection_failed"
            )
            raise
        except UpstreamError:
            await self.notification_repository.mark_failed(
                notification["_id"], "n8n_delivery_failed"
            )
            raise

        sent_notification = await self.notification_repository.mark_sent(
            notification["_id"]
        )

        return {
            "notification_id": str(sent_notification["_id"]),
            "risk_id": sent_notification["risk_id"],
            "destination_id": str(sent_notification["destination_id"]),
            "team_name": sent_notification["team_name"],
            "channel_name": sent_notification.get("channel_name"),
            "status": sent_notification["status"],
            "sent_at": sent_notification["sent_at"]
        }

    async def get_notifications(
        self,
        client_id: str | None = None,
        risk_id: str | None = None,
        status: str | None = None,
        destination_id: str | None = None
    ):
        notifications = await self.notification_repository.get_notifications(
            client_id=client_id,
            risk_id=risk_id,
            status=status,
            destination_id=destination_id
        )
        return [
            serialize_mongo_document(notification)
            for notification in notifications
        ]
