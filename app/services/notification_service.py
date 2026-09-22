from bson import ObjectId

from app.exceptions import (
    ConflictError,
    InactiveResourceError,
    NotFoundError,
    SlackWebhookError,
    SlackWebhookTimeoutError,
)

from app.services.teams_card_renderer import (
    build_teams_notification_payload,
)

from app.services.teams_webhook_service import (
    TeamsWebhookError,
    TeamsWebhookService,
)

from app.services.slack_block_renderer import (
    build_slack_notification_payload,
)

from app.services.slack_webhook_service import (
    SlackWebhookService,
)

from app.utils.mongo_serializer import (
    serialize_mongo_document,
)

from app.utils.mitigation_plan import (
    normalize_mitigation_plan_for_notification,
)


class NotificationService:

    def __init__(
        self,
        notification_repository,
        risk_repository,
        teams_channel_repository,
        slack_destination_repository,
        client_repository,
        risk_destination_override_service,
        n8n_service,
        slack_n8n_service,
    ):
        self.notification_repository = notification_repository
        self.risk_repository = risk_repository
        self.teams_channel_repository = teams_channel_repository
        self.slack_destination_repository = slack_destination_repository
        self.client_repository = client_repository
        self.risk_destination_override_service = (
            risk_destination_override_service
        )

        # Kept temporarily so existing dependency wiring
        # does not break during migration.
        #
        # Notification delivery no longer uses n8n
        # for either Teams or Slack.
        self.n8n_service = n8n_service
        self.slack_n8n_service = slack_n8n_service

    async def _resolve_destination(
        self,
        destination_id: str,
    ):

        if not ObjectId.is_valid(destination_id):
            raise NotFoundError(
                "Destination not found"
            )

        teams_destination = (
            await self.teams_channel_repository.get_by_id(
                destination_id
            )
        )

        if teams_destination is not None:
            return "teams", teams_destination

        slack_destination = (
            await self.slack_destination_repository.get_by_id(
                destination_id
            )
        )

        if slack_destination is not None:
            return "slack", slack_destination

        raise NotFoundError(
            "Destination not found"
        )

    async def trigger_notification(
        self,
        risk_id: str,
        destination_id: str,
    ):

        # =========================================================
        # RESOLVE DESTINATION
        # =========================================================

        platform, destination = (
            await self._resolve_destination(
                destination_id
            )
        )

        if not destination.get(
            "is_active",
            True,
        ):
            raise InactiveResourceError(
                f"{platform.title()} destination is inactive"
            )

        # =========================================================
        # LOAD BASE RISK
        # =========================================================

        risk = (
            await self.risk_repository.get_risk_by_id(
                risk_id
            )
        )

        if risk is None:
            raise NotFoundError(
                "Risk not found"
            )

        # =========================================================
        # APPLY DESTINATION-SPECIFIC RISK OVERRIDE
        #
        # Same base risk can now be sent to multiple destinations
        # while allowing selected fields/blocks to differ.
        #
        # No active override:
        #     base risk remains unchanged.
        #
        # Active override:
        #     base risk + destination override = resolved risk.
        # =========================================================

        risk = (
            await self.risk_destination_override_service.resolve_risk(
                risk=risk,
                destination_id=destination_id,
            )
        )

        # =========================================================
        # LOAD CLIENT
        # =========================================================

        client = (
            await self.client_repository.get_client_by_id(
                str(destination["client_id"])
            )
        )

        if client is None:
            raise NotFoundError(
                "Client not found"
            )

        if not client.get(
            "is_active",
            True,
        ):
            raise InactiveResourceError(
                "Client is inactive"
            )

        # =========================================================
        # RESOLVE PRIVATE WEBHOOK
        # =========================================================

        if platform == "teams":

            destination_webhook_url = (
                destination.get(
                    "teams_webhook_url"
                )
            )

            if not destination_webhook_url:
                raise InactiveResourceError(
                    "Teams webhook is not configured"
                )

        else:

            destination_webhook_url = (
                destination.get(
                    "webhook_url"
                )
            )

            if not destination_webhook_url:
                raise InactiveResourceError(
                    "Slack webhook is not configured"
                )

        # =========================================================
        # DUPLICATE NOTIFICATION PROTECTION
        # =========================================================

        guard_acquired = (
            await self.notification_repository
            .acquire_duplicate_guard(
                risk_id=risk_id,
                destination_id=destination_id,
            )
        )

        if not guard_acquired:
            raise ConflictError(
                "Notification was already triggered recently"
            )

        # =========================================================
        # CREATE PENDING NOTIFICATION
        # =========================================================

        notification_data = {
            "risk_id": risk_id,
            "destination_id": destination["_id"],
            "client_id": destination["client_id"],
            "team_name": (
                destination.get("team_name")
                or ""
            ),
            "channel_name": (
                destination.get("channel_name")
            ),
            "risk_title": (
                risk.get("title")
                or ""
            ),
            "severity": risk.get(
                "severity"
            ),
            "status": "pending",
        }

        if platform == "slack":
            notification_data["platform"] = "slack"

        notification = (
            await self.notification_repository
            .create_notification(
                notification_data
            )
        )

        # =========================================================
        # PREPARE GENERIC RESOLVED RISK PAYLOAD
        # =========================================================

        risk_payload = serialize_mongo_document(
            risk
        )

        risk_payload.pop(
            "id",
            None,
        )

        risk_payload = (
            normalize_mitigation_plan_for_notification(
                risk_payload
            )
        )

        # =========================================================
        # MICROSOFT TEAMS
        #
        # Backend
        #   → Adaptive Card renderer
        #   → Teams webhook
        #
        # n8n is NOT used.
        # =========================================================

        if platform == "teams":

            teams_payload = (
                build_teams_notification_payload(
                    risk_payload
                )
            )

            teams_webhook_service = (
                TeamsWebhookService()
            )

            try:

                await teams_webhook_service.send(
                    webhook_url=destination_webhook_url,
                    payload=teams_payload,
                )

            except TeamsWebhookError:

                await (
                    self.notification_repository
                    .mark_failed(
                        notification["_id"],
                        "teams_delivery_failed",
                    )
                )

                raise

        # =========================================================
        # SLACK
        #
        # Backend
        #   → Slack Block Kit renderer
        #   → Slack Incoming Webhook
        #
        # n8n is NOT used.
        # =========================================================

        else:

            slack_payload = (
                build_slack_notification_payload(
                    risk_payload
                )
            )

            slack_webhook_service = (
                SlackWebhookService()
            )

            try:

                await slack_webhook_service.send(
                    webhook_url=destination_webhook_url,
                    payload=slack_payload,
                )

            except SlackWebhookTimeoutError:

                await (
                    self.notification_repository
                    .mark_failed(
                        notification["_id"],
                        "slack_timeout",
                    )
                )

                raise

            except SlackWebhookError:

                await (
                    self.notification_repository
                    .mark_failed(
                        notification["_id"],
                        "slack_delivery_failed",
                    )
                )

                raise

        # =========================================================
        # DELIVERY SUCCESSFUL
        # =========================================================

        sent_notification = (
            await self.notification_repository
            .mark_sent(
                notification["_id"]
            )
        )

        return {
            "notification_id": str(
                sent_notification["_id"]
            ),
            "risk_id": (
                sent_notification["risk_id"]
            ),
            "destination_id": str(
                sent_notification[
                    "destination_id"
                ]
            ),
            "team_name": (
                sent_notification["team_name"]
            ),
            "channel_name": (
                sent_notification.get(
                    "channel_name"
                )
            ),
            "status": (
                sent_notification["status"]
            ),
            "sent_at": (
                sent_notification["sent_at"]
            ),
        }

    async def get_notifications(
        self,
        client_id: str | None = None,
        risk_id: str | None = None,
        status: str | None = None,
        destination_id: str | None = None,
    ):

        notifications = (
            await self.notification_repository
            .get_notifications(
                client_id=client_id,
                risk_id=risk_id,
                status=status,
                destination_id=destination_id,
            )
        )

        return [
            serialize_mongo_document(
                notification
            )
            for notification in notifications
        ]