import logging

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.schemas.slack_destination import SlackDestinationUpdate
from app.utils.slack_url_parser import (
    is_valid_slack_webhook_url,
    parse_slack_channel_link,
)

logger = logging.getLogger(__name__)


class SlackDestinationService:
    def __init__(
        self,
        slack_destination_repository,
        client_repository,
        slack_webhook_service=None,
    ):
        self.slack_destination_repository = slack_destination_repository
        self.client_repository = client_repository
        self.slack_webhook_service = slack_webhook_service

    @staticmethod
    def _parse_channel_link(channel_link: str) -> tuple[str, str, str]:
        normalized_link = channel_link.strip()
        parsed = parse_slack_channel_link(normalized_link)
        workspace_domain = parsed.get("workspace_domain")
        channel_id = parsed.get("channel_id")
        if not workspace_domain or not channel_id:
            raise ValueError("Invalid Slack channel link")
        return normalized_link, workspace_domain, channel_id

    @staticmethod
    def _validate_webhook(webhook_url: str) -> str:
        normalized_webhook = webhook_url.strip()
        if not is_valid_slack_webhook_url(normalized_webhook):
            raise ValueError("Invalid Slack webhook URL")
        return normalized_webhook

    async def _get_client(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            raise LookupError("Client not found")
        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        return client

    async def create_destination(
        self,
        client_id: str,
        channel_link: str,
        channel_name: str,
        webhook_url: str,
    ):
        client = await self._get_client(client_id)
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")

        normalized_name = channel_name.strip()
        if not normalized_name:
            raise ValueError("Invalid channel name")
        normalized_link, workspace_domain, channel_id = self._parse_channel_link(
            channel_link
        )
        normalized_webhook = self._validate_webhook(webhook_url)

        duplicate = await self.slack_destination_repository.get_active_by_identity(
            client_id, workspace_domain, channel_id
        )
        if duplicate is not None:
            raise FileExistsError("This Slack channel is already configured")

        try:
            return await self.slack_destination_repository.create_destination(
                client_id=client_id,
                workspace_domain=workspace_domain,
                channel_id=channel_id,
                channel_name=normalized_name,
                channel_link=normalized_link,
                webhook_url=normalized_webhook,
            )
        except DuplicateKeyError as exc:
            raise FileExistsError(
                "This Slack channel is already configured"
            ) from exc

    async def get_destination_by_id(self, destination_id: str):
        if not ObjectId.is_valid(destination_id):
            raise LookupError("Slack destination not found")
        destination = await self.slack_destination_repository.get_by_id(
            destination_id
        )
        if destination is None:
            raise LookupError("Slack destination not found")
        return destination

    async def get_destinations_by_client(self, client_id: str):
        await self._get_client(client_id)
        return await self.slack_destination_repository.get_destinations_by_client(
            client_id
        )

    async def update_destination(
        self, destination_id: str, update_data: SlackDestinationUpdate
    ):
        if not ObjectId.is_valid(destination_id):
            raise ValueError("Invalid Slack destination ID")
        existing = await self.slack_destination_repository.get_by_id(destination_id)
        if existing is None:
            raise LookupError("Slack destination not found")

        updates = update_data.model_dump(exclude_unset=True)
        if "channel_name" in updates:
            if updates["channel_name"] is None:
                raise ValueError("Invalid channel name")
            updates["channel_name"] = updates["channel_name"].strip()
            if not updates["channel_name"]:
                raise ValueError("Invalid channel name")

        if "webhook_url" in updates:
            if updates["webhook_url"] is None:
                updates.pop("webhook_url")
            else:
                updates["webhook_url"] = self._validate_webhook(
                    updates["webhook_url"]
                )

        workspace_domain = existing["workspace_domain"]
        channel_id = existing["channel_id"]
        if "channel_link" in updates:
            if updates["channel_link"] is None:
                raise ValueError("Invalid Slack channel link")
            channel_link, workspace_domain, channel_id = self._parse_channel_link(
                updates["channel_link"]
            )
            updates.update(
                {
                    "channel_link": channel_link,
                    "workspace_domain": workspace_domain,
                    "channel_id": channel_id,
                }
            )

        target_active = updates.get("is_active", existing.get("is_active", True))
        if target_active:
            duplicate = (
                await self.slack_destination_repository.get_active_by_identity(
                    str(existing["client_id"]),
                    workspace_domain,
                    channel_id,
                    exclude_destination_id=destination_id,
                )
            )
            if duplicate is not None:
                raise FileExistsError("This Slack channel is already configured")

        try:
            updated = await self.slack_destination_repository.update_destination(
                destination_id, updates
            )
        except DuplicateKeyError as exc:
            raise FileExistsError(
                "This Slack channel is already configured"
            ) from exc
        if updated is None:
            raise LookupError("Slack destination not found")
        return updated

    async def delete_destination(self, destination_id: str):
        await self.get_destination_by_id(destination_id)
        deleted = await self.slack_destination_repository.soft_delete(destination_id)
        if deleted is None:
            raise LookupError("Slack destination not found")
        return deleted

    async def test_destination(self, destination_id: str):
        destination = await self.get_destination_by_id(destination_id)
        if not destination.get("is_active", True):
            raise ValueError("Slack destination is inactive")

        client = await self.client_repository.get_client_by_id(
            str(destination["client_id"])
        )
        if client is None:
            raise ValueError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")

        webhook_url = destination.get("webhook_url")
        if not webhook_url:
            raise ValueError("Slack webhook is not configured")
        if self.slack_webhook_service is None:
            raise RuntimeError("Slack webhook service is not configured")

        await self.slack_webhook_service.send_test_message(webhook_url)
