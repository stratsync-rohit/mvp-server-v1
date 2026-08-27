import logging

from bson import ObjectId

from app.utils.teams_url_parser import parse_teams_channel_url
from app.schemas.teams_channel import TeamsChannelUpdate

logger = logging.getLogger(__name__)


class TeamsChannelService:

    def __init__(
        self,
        teams_channel_repository,
        client_repository,
        n8n_service=None
    ):
        self.teams_channel_repository = teams_channel_repository
        self.client_repository = client_repository
        self.n8n_service = n8n_service


    async def get_channel_by_id(self, destination_id: str):

        channel = await self.teams_channel_repository.get_by_id(
            destination_id
        )

        if channel is None:
            logger.warning(
                "teams_destination_lookup_failed destination_id=%s "
                "error_code=destination_not_found",
                destination_id,
            )
            raise ValueError("Teams destination not found")

        return channel


    async def test_channel(self, destination_id: str):

        if not ObjectId.is_valid(destination_id):
            logger.warning(
                "test_notification_validation_failed destination_id=%s "
                "error_code=invalid_destination_id",
                destination_id,
            )
            raise ValueError("Teams destination not found")

        channel = await self.get_channel_by_id(destination_id)

        if not channel.get("is_active", True):
            logger.warning(
                "test_notification_validation_failed destination_id=%s "
                "error_code=destination_inactive",
                destination_id,
            )
            raise ValueError("Teams destination is inactive")

        client = await self.client_repository.get_client_by_id(
            str(channel["client_id"])
        )
        if client is None:
            logger.warning(
                "test_notification_validation_failed destination_id=%s "
                "error_code=client_not_found",
                destination_id,
            )
            raise ValueError("Client not found")
        if not client.get("is_active", True):
            logger.warning(
                "test_notification_validation_failed destination_id=%s "
                "error_code=client_inactive",
                destination_id,
            )
            raise ValueError("Client is inactive")

        teams_webhook_url = channel.get("teams_webhook_url")

        if not teams_webhook_url:
            logger.warning(
                "test_notification_validation_failed destination_id=%s "
                "error_code=teams_webhook_missing",
                destination_id,
            )
            raise ValueError("Teams webhook is not configured")

        team_name = channel.get("team_name") or ""
        channel_name = channel.get("channel_name") or ""

        payload = {
            "teams_webhook_url": teams_webhook_url,
            "risk": {
                "risk_id": "TEST-INTEGRATION",
                "title": "StratSync Teams Integration Test",
                "severity": "low",
                "severity_label": "Test",
                "subtitle": f"{team_name} · {channel_name}",
                "summary": (
                    "Your StratSync Microsoft Teams integration is "
                    "configured correctly."
                ),
                "sender": {
                    "name": "StratSync RRM",
                    "source": "StratSync RRM",
                    "risk_id": "TEST-INTEGRATION",
                    "timestamp": "Integration Test"
                },
                "metrics": [
                    {
                        "label": "STATUS",
                        "value": "Connected",
                        "status": "neutral"
                    }
                ],
                "details": {
                    "facts": [
                        {"label": "Team", "value": team_name},
                        {"label": "Channel", "value": channel_name}
                    ],
                    "groups": []
                },
                "mitigation": {
                    "summary": "No action required.",
                    "steps": [],
                    "last_updated": "",
                    "next_action": ""
                }
            }
        }

        if self.n8n_service is None:
            raise RuntimeError("Notification service is not configured")

        await self.n8n_service.trigger_notification(payload)

        return {
            "destination_id": str(channel["_id"]),
            "team_name": team_name,
            "channel_name": channel_name
        }


    async def get_channels_by_client(self, client_id: str):

        client = await self.client_repository.get_client_by_id(
            client_id
        )

        if client is None:
            raise ValueError("Client not found")

        channels = await self.teams_channel_repository.get_channels_by_client(
            client_id
        )

        return channels


    async def update_channel(
        self,
        destination_id: str,
        update_data: TeamsChannelUpdate
    ):
        if not ObjectId.is_valid(destination_id):
            raise ValueError("Invalid Teams destination ID")

        existing = await self.teams_channel_repository.get_by_id(
            destination_id
        )
        if existing is None:
            raise LookupError("Teams destination not found")

        updates = update_data.model_dump(exclude_unset=True)

        requested_team_name = updates.get("team_name")
        if requested_team_name is not None:
            requested_team_name = requested_team_name.strip()
            updates["team_name"] = requested_team_name
            if len(requested_team_name) < 2:
                raise ValueError("Invalid team name")

        webhook_url = updates.get("teams_webhook_url")
        if "teams_webhook_url" in updates and webhook_url is None:
            updates.pop("teams_webhook_url", None)
        elif webhook_url is not None:
            webhook_url = str(webhook_url).strip()
            if webhook_url:
                duplicate = (
                    await self.teams_channel_repository.get_by_webhook_url(
                        webhook_url
                    )
                )
                if (
                    duplicate is not None
                    and duplicate["_id"] != existing["_id"]
                ):
                    raise ValueError(
                        "This Teams webhook is already configured"
                    )
                updates["teams_webhook_url"] = webhook_url
            else:
                updates.pop("teams_webhook_url", None)

        old_team_id = existing.get("team_id")
        target_team_id = old_team_id
        channel_url = updates.get("channel_url")
        if channel_url is not None:
            channel_url = str(channel_url).strip()
            updates["channel_url"] = channel_url
            if (
                channel_url != existing.get("channel_url")
                or not existing.get("team_id")
                or not existing.get("channel_id")
            ):
                parsed = parse_teams_channel_url(channel_url)
                required_metadata = (
                    parsed.get("channel_id"),
                    parsed.get("team_id"),
                    parsed.get("tenant_id"),
                )
                if not all(required_metadata):
                    raise ValueError("Invalid Teams channel link")

                target_team_id = parsed["team_id"]

                duplicate_channel = (
                    await self.teams_channel_repository.get_by_teams_identity(
                        client_id=str(existing["client_id"]),
                        tenant_id=parsed["tenant_id"],
                        team_id=parsed["team_id"],
                        channel_id=parsed["channel_id"],
                    )
                )
                if (
                    duplicate_channel is not None
                    and duplicate_channel["_id"] != existing["_id"]
                ):
                    raise ValueError(
                        "This Teams channel is already configured"
                    )

                updates.update({
                    "channel_name": parsed.get("channel_name"),
                    "tenant_id": parsed.get("tenant_id"),
                    "team_id": parsed.get("team_id"),
                    "channel_id": parsed.get("channel_id"),
                })

        client_id = str(existing["client_id"])
        if target_team_id and target_team_id != old_team_id:
            existing_team = (
                await self.teams_channel_repository.find_by_client_and_team_id(
                    client_id,
                    target_team_id,
                )
            )
            if (
                existing_team is not None
                and existing_team["_id"] != existing["_id"]
            ):
                updates["team_name"] = existing_team["team_name"]
            elif requested_team_name is not None:
                updates["team_name"] = requested_team_name
            else:
                updates["team_name"] = existing["team_name"]
        elif target_team_id and requested_team_name is not None:
            await self.teams_channel_repository.update_team_name(
                client_id,
                target_team_id,
                requested_team_name,
            )

        updated = await self.teams_channel_repository.update_channel(
            destination_id,
            updates,
        )
        if updated is None:
            raise LookupError("Teams destination not found")
        return updated


    async def create_channel(
        self,
        client_id: str,
        team_name: str,
        channel_url: str,
        teams_webhook_url: str
    ):

        # ------------------------------------------------------
        # 1. Validate client ID
        # ------------------------------------------------------

        if not ObjectId.is_valid(client_id):
            raise ValueError("Client not found")


        # ------------------------------------------------------
        # 2. Check client exists
        # ------------------------------------------------------

        client = await self.client_repository.get_client_by_id(
            client_id
        )

        if client is None:
            raise ValueError("Client not found")


        # ------------------------------------------------------
        # 3. Client active hona chahiye
        # ------------------------------------------------------

        if not client.get("is_active", True):
            raise ValueError("Client is inactive")


        # ------------------------------------------------------
        # 4. Clean team name
        # ------------------------------------------------------

        team_name = team_name.strip()

        if len(team_name) < 2:
            raise ValueError("Invalid team name")


        # ------------------------------------------------------
        # 5. Teams Copy Link parse karo
        # ------------------------------------------------------

        parsed_data = parse_teams_channel_url(
            channel_url
        )

        channel_name = parsed_data.get("channel_name")
        tenant_id = parsed_data.get("tenant_id")
        team_id = parsed_data.get("team_id")
        channel_id = parsed_data.get("channel_id")

        if not team_id or not channel_id or not tenant_id:
            raise ValueError("Invalid Teams channel link")

        existing_team_destination = (
            await self.teams_channel_repository.find_by_client_and_team_id(
                client_id,
                team_id,
            )
        )
        if existing_team_destination is not None:
            team_name = existing_team_destination["team_name"]


        # ------------------------------------------------------
        # 6. Duplicate webhook check
        # ------------------------------------------------------

        existing_webhook = (
            await self.teams_channel_repository.get_by_webhook_url(
                teams_webhook_url
            )
        )

        if existing_webhook is not None:
            raise ValueError(
                "This Teams webhook is already configured"
            )


        # ------------------------------------------------------
        # 7. Duplicate Teams channel check
        # ------------------------------------------------------

        if tenant_id and team_id and channel_id:

            existing_channel = (
                await self.teams_channel_repository.get_by_teams_identity(
                    client_id=client_id,
                    tenant_id=tenant_id,
                    team_id=team_id,
                    channel_id=channel_id
                )
            )

            if existing_channel is not None:
                raise ValueError(
                    "This Teams channel is already configured"
                )


        # ------------------------------------------------------
        # 8. MongoDB me destination create karo
        # ------------------------------------------------------

        channel = (
            await self.teams_channel_repository.create_channel(
                client_id=client_id,
                team_name=team_name,
                channel_url=channel_url,
                teams_webhook_url=teams_webhook_url,
                channel_name=channel_name,
                tenant_id=tenant_id,
                team_id=team_id,
                channel_id=channel_id
            )
        )

        return channel
