from app.exceptions import (
    ConflictError,
    InactiveResourceError,
    NotFoundError,
    UpstreamConnectionError,
    UpstreamError,
    UpstreamTimeoutError
)
from app.utils.mongo_serializer import serialize_mongo_document


class NotificationService:

    def __init__(
        self,
        notification_repository,
        risk_repository,
        teams_channel_repository,
        client_repository,
        n8n_service
    ):
        self.notification_repository = notification_repository
        self.risk_repository = risk_repository
        self.teams_channel_repository = teams_channel_repository
        self.client_repository = client_repository
        self.n8n_service = n8n_service

    async def trigger_notification(
        self,
        risk_id: str,
        destination_id: str
    ):
        risk = await self.risk_repository.get_risk_by_id(risk_id)
        if risk is None:
            raise NotFoundError("Risk not found")

        destination = await self.teams_channel_repository.get_by_id(
            destination_id
        )
        if destination is None:
            raise NotFoundError("Teams destination not found")

        if not destination.get("is_active", True):
            raise InactiveResourceError("Teams destination is inactive")

        client = await self.client_repository.get_client_by_id(
            str(destination["client_id"])
        )
        if client is None:
            raise NotFoundError("Client not found")
        if not client.get("is_active", True):
            raise InactiveResourceError("Client is inactive")

        teams_webhook_url = destination.get("teams_webhook_url")
        if not teams_webhook_url:
            raise InactiveResourceError("Teams webhook is not configured")

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

        notification = await self.notification_repository.create_notification({
            "risk_id": risk_id,
            "destination_id": destination["_id"],
            "client_id": destination["client_id"],
            "team_name": destination.get("team_name") or "",
            "channel_name": destination.get("channel_name"),
            "risk_title": risk.get("title") or "",
            "severity": risk.get("severity"),
            "status": "pending"
        })

        risk_payload = serialize_mongo_document(risk)
        risk_payload.pop("id", None)
        payload = {
            "teams_webhook_url": teams_webhook_url,
            "risk": risk_payload
        }

        try:
            await self.n8n_service.trigger_notification(payload)
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
