import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time

from bson import ObjectId

from app.config import Settings
from app.exceptions import (
    SlackOAuthStateConfigurationError,
    SlackOAuthStateError,
)


class SlackOAuthStateService:
    """Stateless, signed OAuth state carrying a validated client ID."""

    STATE_VERSION = 1
    MAX_AGE_SECONDS = 10 * 60
    FUTURE_CLOCK_SKEW_SECONDS = 30

    def __init__(self, settings: Settings, client_repository):
        self.settings = settings
        self.client_repository = client_repository

    def _secret(self) -> bytes:
        # A dedicated secret is preferred. Falling back to the Slack client
        # secret keeps existing deployments secure without requiring an
        # immediate second secret during rollout.
        secret = (
            self.settings.slack_oauth_state_secret
            or self.settings.slack_client_secret
        )
        if not secret:
            raise SlackOAuthStateConfigurationError(
                "Slack OAuth state signing is not configured"
            )
        return secret.encode("utf-8")

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))

    def _sign(self, encoded_payload: str) -> str:
        signature = hmac.new(
            self._secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return self._encode(signature)

    async def create_state(self, client_id: str) -> str:
        if not ObjectId.is_valid(client_id):
            raise LookupError("Client not found")

        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")

        payload = {
            "v": self.STATE_VERSION,
            "client_id": client_id,
            "issued_at": int(time.time()),
            "nonce": secrets.token_urlsafe(16),
        }
        encoded_payload = self._encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
        return f"{encoded_payload}.{self._sign(encoded_payload)}"

    def decode_state(self, state: str) -> str:
        try:
            encoded_payload, encoded_signature = state.split(".", 1)
            expected_signature = self._sign(encoded_payload)
            if not hmac.compare_digest(
                encoded_signature,
                expected_signature,
            ):
                raise ValueError

            payload = json.loads(self._decode(encoded_payload).decode("utf-8"))
            issued_at = payload["issued_at"]
            client_id = payload["client_id"]
            now = int(time.time())

            if payload.get("v") != self.STATE_VERSION:
                raise ValueError
            if not isinstance(issued_at, int) or isinstance(issued_at, bool):
                raise ValueError
            if issued_at > now + self.FUTURE_CLOCK_SKEW_SECONDS:
                raise ValueError
            if now - issued_at > self.MAX_AGE_SECONDS:
                raise ValueError
            if not isinstance(client_id, str) or not ObjectId.is_valid(client_id):
                raise ValueError

            return client_id
        except (
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
            ValueError,
            binascii.Error,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise SlackOAuthStateError("Invalid or expired Slack OAuth state") from exc

    async def validate_state(self, state: str) -> str:
        client_id = self.decode_state(state)
        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")
        return client_id
