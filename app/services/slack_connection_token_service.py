import secrets

from bson import ObjectId
from pymongo.errors import DuplicateKeyError


class SlackConnectionTokenService:
    """Creates and resolves reusable client-scoped Slack connect URLs."""

    TOKEN_BYTES = 32

    def __init__(self, repository, client_repository):
        self.repository = repository
        self.client_repository = client_repository

    async def get_or_create_for_client(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            raise LookupError("Client not found")

        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")

        existing = await self.repository.get_active_by_client_id(client_id)
        if existing is not None:
            return existing

        try:
            return await self.repository.create(
                secrets.token_urlsafe(self.TOKEN_BYTES), client_id
            )
        except DuplicateKeyError:
            existing = await self.repository.get_active_by_client_id(client_id)
            if existing is None:
                raise
            return existing

    async def resolve(self, token: str):
        connection = await self.repository.get_active_by_token(token)
        if connection is None:
            raise LookupError("Slack connection token not found")

        client_id = connection.get("client_id")
        if not isinstance(client_id, ObjectId):
            raise LookupError("Slack connection token not found")

        client = await self.client_repository.get_client_by_id(str(client_id))
        if client is None:
            raise LookupError("Slack connection token not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")
        return connection
