import logging

from bson import ObjectId

from app.exceptions import ConflictError


logger = logging.getLogger(__name__)


class SlackWorkspaceInstallationService:
    WORKSPACE_CONFLICT_MESSAGE = (
        "This Slack workspace is already connected to another "
        "StratSync client."
    )
    LEGACY_CONFLICT_MESSAGE = (
        "Slack workspace ownership data is inconsistent and requires "
        "manual cleanup."
    )

    def __init__(
        self,
        repository,
        client_repository=None,
        destination_repository=None,
    ):
        self.repository = repository
        self.client_repository = client_repository
        self.destination_repository = destination_repository

    @staticmethod
    def _installation_data(installation):
        if hasattr(installation, "model_dump"):
            return installation.model_dump()
        return dict(installation)

    @staticmethod
    def _owner_string(value):
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, str) and ObjectId.is_valid(value):
            return value
        return None

    async def _validate_client(self, client_id: str) -> ObjectId:
        if not ObjectId.is_valid(client_id):
            raise LookupError("Client not found")
        if self.client_repository is None:
            raise LookupError("Client not found")

        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")
        return ObjectId(client_id)

    async def _resolve_workspace_ownership(
        self,
        workspace_id: str,
        trusted_client_id: ObjectId,
    ) -> None:
        existing = await self.repository.get_by_team_id(workspace_id)
        installation_owner = (
            self._owner_string(existing.get("client_id"))
            if existing is not None
            else None
        )

        if existing is not None and existing.get("client_id") is not None:
            if installation_owner is None:
                logger.error(
                    "slack_workspace_ownership_conflict "
                    "workspace_id=%s reason=invalid_owner",
                    workspace_id,
                )
                raise ConflictError(self.LEGACY_CONFLICT_MESSAGE)

        destination_owners = set()
        if self.destination_repository is not None:
            destination_owners = set(
                await self.destination_repository.get_oauth_workspace_client_ids(
                    workspace_id
                )
            )

        known_owners = set(destination_owners)
        if installation_owner is not None:
            known_owners.add(installation_owner)

        if len(known_owners) > 1:
            logger.error(
                "slack_workspace_ownership_conflict "
                "workspace_id=%s reason=inconsistent_legacy_data",
                workspace_id,
            )
            raise ConflictError(self.LEGACY_CONFLICT_MESSAGE)

        trusted_owner = str(trusted_client_id)
        established_owner = next(iter(known_owners), None)
        if established_owner is not None and established_owner != trusted_owner:
            logger.warning(
                "slack_workspace_ownership_conflict workspace_id=%s",
                workspace_id,
            )
            raise ConflictError(self.WORKSPACE_CONFLICT_MESSAGE)

        if established_owner == trusted_owner:
            logger.info(
                "slack_workspace_ownership_verified client_id=%s workspace_id=%s",
                trusted_owner,
                workspace_id,
            )
        else:
            logger.info(
                "slack_workspace_ownership_claimed client_id=%s workspace_id=%s",
                trusted_owner,
                workspace_id,
            )

    async def save_installation(
        self,
        installation,
        client_id: str | None = None,
    ):
        if client_id is None:
            raise LookupError("Client not found")

        trusted_client_id = await self._validate_client(client_id)
        installation_data = self._installation_data(installation)
        workspace_id = installation_data.get("slack_team_id")
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("Slack workspace ID is required")

        await self._resolve_workspace_ownership(
            workspace_id,
            trusted_client_id,
        )
        return await self.repository.upsert_installation(
            installation_data,
            client_id=trusted_client_id,
        )

    async def save_installation_and_destination(
        self,
        installation,
        client_id: str | None = None,
    ):
        """Validate workspace ownership, then persist installation/channel."""
        if client_id is None:
            raise LookupError("Client not found")

        trusted_client_id = await self._validate_client(client_id)
        installation_data = self._installation_data(installation)
        workspace_id = installation_data.get("slack_team_id")
        workspace_name = installation_data.get("slack_team_name")
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("Slack workspace ID is required")

        await self._resolve_workspace_ownership(
            workspace_id,
            trusted_client_id,
        )

        webhook = installation_data.get("incoming_webhook")
        channel_id = webhook.get("channel_id") if isinstance(webhook, dict) else None
        channel_name = webhook.get("channel") if isinstance(webhook, dict) else None
        webhook_url = webhook.get("url") if isinstance(webhook, dict) else None

        if (
            self.destination_repository is not None
            and all(
                isinstance(value, str) and value.strip()
                for value in (
                    workspace_id,
                    workspace_name,
                    channel_id,
                    channel_name,
                    webhook_url,
                )
            )
        ):
            existing_owner = await self.destination_repository.get_oauth_owner(
                workspace_id,
                channel_id,
            )
            if (
                existing_owner is not None
                and existing_owner.get("client_id") != trusted_client_id
            ):
                logger.warning(
                    "slack_workspace_ownership_conflict workspace_id=%s",
                    workspace_id,
                )
                raise ConflictError(self.WORKSPACE_CONFLICT_MESSAGE)

        saved_installation = await self.repository.upsert_installation(
            installation_data,
            client_id=trusted_client_id,
        )

        if (
            self.destination_repository is None
            or not isinstance(webhook, dict)
        ):
            return saved_installation, None

        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                workspace_id,
                workspace_name,
                channel_id,
                channel_name,
                webhook_url,
            )
        ):
            return saved_installation, None

        destination = await self.destination_repository.upsert_oauth_destination(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            channel_id=channel_id,
            channel_name=channel_name,
            webhook_url=webhook_url,
            configuration_url=webhook.get("configuration_url"),
            client_id=trusted_client_id,
        )

        return saved_installation, destination
