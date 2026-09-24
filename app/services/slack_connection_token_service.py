import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from cryptography.fernet import Fernet, InvalidToken
from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.exceptions import (
    SlackConnectionTokenConfigurationError,
    SlackConnectionTokenExpiredError,
)


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Treat legacy/mock-driver naive BSON values as UTC on read."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class _StoredTokenIntegrityError(Exception):
    pass


class SlackConnectionTokenService:
    """Creates, recovers, rotates, and resolves secure Slack connect URLs."""

    TOKEN_BYTES = 32
    TOKEN_LIFETIME = timedelta(hours=20)

    def __init__(self, repository, client_repository, settings=None, now_fn=None):
        self.repository = repository
        self.client_repository = client_repository
        self.settings = settings or get_settings()
        self.now_fn = now_fn or _utc_now

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def _fernet(self) -> Fernet:
        key = getattr(self.settings, "slack_connection_token_encryption_key", None)
        if not isinstance(key, str) or not key:
            raise SlackConnectionTokenConfigurationError(
                "Slack connection token encryption is not configured"
            )
        try:
            return Fernet(key.encode("ascii"))
        except (UnicodeEncodeError, TypeError, ValueError) as exc:
            raise SlackConnectionTokenConfigurationError(
                "Slack connection token encryption is not configured"
            ) from exc

    def _encrypt(self, raw_token: str) -> str:
        return self._fernet().encrypt(raw_token.encode("utf-8")).decode("ascii")

    def _decrypt_and_verify(self, connection: dict) -> str:
        ciphertext = connection.get("token_ciphertext")
        expected_hash = connection.get("token_hash")
        if not isinstance(ciphertext, str) or not isinstance(expected_hash, str):
            raise _StoredTokenIntegrityError

        try:
            raw_token = self._fernet().decrypt(ciphertext.encode("ascii")).decode(
                "utf-8"
            )
        except (UnicodeEncodeError, UnicodeDecodeError, InvalidToken) as exc:
            raise _StoredTokenIntegrityError from exc

        if not hmac.compare_digest(self.hash_token(raw_token), expected_hash):
            raise _StoredTokenIntegrityError
        return raw_token

    async def get_or_create_for_client(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            raise LookupError("Client not found")

        client = await self.client_repository.get_client_by_id(client_id)
        if client is None:
            raise LookupError("Client not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")

        now = self.now_fn()
        existing = await self.repository.get_active_by_client_id(client_id, now=now)
        if existing is not None:
            try:
                raw_token = self._decrypt_and_verify(existing)
            except _StoredTokenIntegrityError:
                await self.repository.deactivate_by_id(existing["_id"], now=now)
            else:
                logger.info(
                    "slack_connection_token_reused client_id=%s expires_at=%s",
                    client_id,
                    existing["expires_at"],
                )
                existing["raw_token"] = raw_token
                return existing

        # Expiration and legacy records are handled lazily. No raw legacy token
        # is read and no plaintext fallback is permitted.
        expired = await self.repository.deactivate_expired_for_client(
            client_id, now=now
        )
        if expired is not None:
            logger.info(
                "slack_connection_token_expired client_id=%s", client_id
            )
        await self.repository.deactivate_legacy_for_client(client_id, now=now)

        try:
            connection = await self._create_new(client_id, now)
        except DuplicateKeyError:
            # The partial unique active-client index makes this the safe winner
            # path when two requests rotate concurrently.
            existing = await self.repository.get_active_by_client_id(
                client_id, now=self.now_fn()
            )
            if existing is None:
                raise
            existing["raw_token"] = self._decrypt_and_verify(existing)
            return existing

        logger.info(
            "slack_connection_token_%s client_id=%s expires_at=%s",
            "rotated" if expired is not None else "created",
            client_id,
            connection["expires_at"],
        )
        return connection

    async def _create_new(self, client_id: str, now: datetime):
        raw_token = secrets.token_urlsafe(self.TOKEN_BYTES)
        connection = await self.repository.create(
            client_id=client_id,
            token_hash=self.hash_token(raw_token),
            token_ciphertext=self._encrypt(raw_token),
            created_at=now,
            expires_at=now + self.TOKEN_LIFETIME,
        )
        connection["raw_token"] = raw_token
        return connection

    async def resolve(self, token: str):
        if not isinstance(token, str) or not token:
            raise LookupError("Slack connection token not found")

        # Authentication is always a hash lookup. Ciphertext is never used as
        # an authentication comparison and is not decrypted on this path.
        connection = await self.repository.get_by_token_hash(self.hash_token(token))
        if connection is None:
            raise LookupError("Slack connection token not found")

        now = self.now_fn()
        if not connection.get("is_active", False):
            raise LookupError("Slack connection token not found")
        expires_at = connection.get("expires_at")
        if not isinstance(expires_at, datetime) or now >= _as_utc(expires_at):
            await self.repository.deactivate_by_id(connection["_id"], now=now)
            raise SlackConnectionTokenExpiredError(
                "This Slack connection link has expired. Please request a new link."
            )

        client_id = connection.get("client_id")
        if not isinstance(client_id, ObjectId):
            raise LookupError("Slack connection token not found")

        client = await self.client_repository.get_client_by_id(str(client_id))
        if client is None:
            raise LookupError("Slack connection token not found")
        if not client.get("is_active", True):
            raise ValueError("Client is inactive")
        return connection
