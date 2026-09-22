from bson import ObjectId


class SlackWorkspaceInstallationService:
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
            # Keep the document shape explicit (including nullable Slack
            # fields such as enterprise_id) while the repository controls the
            # client association separately.
            return installation.model_dump()

        return dict(installation)

    async def save_installation(
        self,
        installation,
        client_id: str | None = None,
    ):
        if client_id is not None:
            if not ObjectId.is_valid(client_id):
                raise LookupError("Client not found")

            if self.client_repository is None:
                raise LookupError("Client not found")

            client = await self.client_repository.get_client_by_id(client_id)
            if client is None:
                raise LookupError("Client not found")

        installation_data = self._installation_data(installation)

        # Workspace OAuth data remains workspace-level. Any validated client
        # association is applied only to the destination below.
        return await self.repository.upsert_installation(
            installation_data,
        )

    async def save_installation_and_destination(
        self,
        installation,
        client_id: str | None = None,
    ):
        """Persist workspace OAuth data and its optional webhook destination."""
        installation_data = self._installation_data(installation)
        trusted_client_id = None
        if client_id is not None:
            if not ObjectId.is_valid(client_id):
                raise LookupError("Client not found")
            if self.client_repository is None:
                raise LookupError("Client not found")
            client = await self.client_repository.get_client_by_id(client_id)
            if client is None:
                raise LookupError("Client not found")
            if not client.get("is_active", True):
                raise ValueError("Client is inactive")
            trusted_client_id = ObjectId(client_id)

        saved_installation = await self.save_installation(
            installation_data,
        )

        webhook = installation_data.get("incoming_webhook")
        if (
            self.destination_repository is None
            or not isinstance(webhook, dict)
        ):
            return saved_installation, None

        workspace_id = installation_data.get("slack_team_id")
        workspace_name = installation_data.get("slack_team_name")
        channel_id = webhook.get("channel_id")
        channel_name = webhook.get("channel")
        webhook_url = webhook.get("url")

        # Slack may issue a valid workspace installation without an incoming
        # webhook. In that case retain the workspace and skip destination
        # creation rather than creating an unusable record.
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
