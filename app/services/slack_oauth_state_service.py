import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.config import Settings
from app.exceptions import SlackOAuthStateConfigurationError, SlackOAuthStateError


class SlackOAuthStateService:
    """Persistent, short-lived and one-time Slack OAuth state."""

    MAX_AGE_SECONDS = 10 * 60

    def __init__(self, settings: Settings, client_repository, repository=None):
        self.settings = settings
        self.client_repository = client_repository
        self.repository = repository

    async def create_state(self, client_id: str, connection_token_id=None) -> str:
        if self.repository is None:
            raise SlackOAuthStateConfigurationError(
                "Slack OAuth state storage is not configured"
            )
        if not ObjectId.is_valid(client_id):
            raise LookupError("Client not found")

        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")

        state = secrets.token_urlsafe(32)
        await self.repository.create(
            state=state,
            client_id=client_id,
            connection_token_id=connection_token_id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=self.MAX_AGE_SECONDS),
        )
        return state

    async def validate_state(self, state: str) -> str:
        if self.repository is None:
            raise SlackOAuthStateConfigurationError(
                "Slack OAuth state storage is not configured"
            )

        record = await self.repository.get_by_state(state)
        if record is None or record.get("used") is True:
            raise SlackOAuthStateError("Invalid or expired Slack OAuth state")

        expires_at = record.get("expires_at")
        if not isinstance(expires_at, datetime):
            raise SlackOAuthStateError("Invalid or expired Slack OAuth state")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise SlackOAuthStateError("Invalid or expired Slack OAuth state")

        client_id = record.get("client_id")
        if not isinstance(client_id, ObjectId):
            raise SlackOAuthStateError("Invalid or expired Slack OAuth state")

        client = await self.client_repository.get_client_by_id(str(client_id))
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")
        return str(client_id)

    async def mark_used(self, state: str) -> None:
        if self.repository is None:
            raise SlackOAuthStateConfigurationError(
                "Slack OAuth state storage is not configured"
            )
        if await self.repository.mark_used(state) is None:
            raise SlackOAuthStateError("Invalid or expired Slack OAuth state")
