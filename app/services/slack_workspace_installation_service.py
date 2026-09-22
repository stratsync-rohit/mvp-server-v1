from bson import ObjectId


class SlackWorkspaceInstallationService:
    def __init__(self, repository, client_repository=None):
        self.repository = repository
        self.client_repository = client_repository

    async def save_installation(
        self,
        installation,
        client_id: str | None = None,
    ):
        trusted_client_id = None

        if client_id is not None:
            if not ObjectId.is_valid(client_id):
                raise LookupError("Client not found")

            if self.client_repository is None:
                raise LookupError("Client not found")

            client = await self.client_repository.get_client_by_id(client_id)
            if client is None:
                raise LookupError("Client not found")

            trusted_client_id = ObjectId(client_id)

        if hasattr(installation, "model_dump"):
            # Keep the document shape explicit (including nullable Slack
            # fields such as enterprise_id) while the repository controls the
            # client association separately.
            installation_data = installation.model_dump()
        else:
            installation_data = dict(installation)

        # No browser-provided client_id is accepted here. A future signed or
        # temporary state flow can pass a validated association explicitly.
        return await self.repository.upsert_installation(
            installation_data,
            client_id=trusted_client_id,
        )
