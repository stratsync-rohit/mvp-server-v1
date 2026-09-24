from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SlackConnectionTokenRepository:
    """Persistence for hashed, client-scoped Slack connection tokens."""

    def __init__(self, database):
        self.collection = database["slack_connection_tokens"]

    async def get_active_by_token_hash(
        self, token_hash: str, *, now: datetime | None = None
    ):
        if not isinstance(token_hash, str) or not token_hash:
            return None
        now = now or _utc_now()
        return await self.collection.find_one(
            {
                "token_hash": token_hash,
                "is_active": True,
                "expires_at": {"$gt": now},
            }
        )

    async def get_by_token_hash(self, token_hash: str):
        if not isinstance(token_hash, str) or not token_hash:
            return None
        return await self.collection.find_one({"token_hash": token_hash})

    async def get_active_by_client_id(
        self, client_id: str, *, now: datetime | None = None
    ):
        if not ObjectId.is_valid(client_id):
            return None
        now = now or _utc_now()
        return await self.collection.find_one(
            {
                "client_id": ObjectId(client_id),
                "is_active": True,
                "expires_at": {"$gt": now},
                "token_hash": {"$exists": True},
                "token_ciphertext": {"$exists": True},
            }
        )

    async def create(
        self,
        *,
        client_id: str,
        token_hash: str,
        token_ciphertext: str,
        created_at: datetime,
        expires_at: datetime,
    ):
        document = {
            "client_id": ObjectId(client_id),
            "token_hash": token_hash,
            "token_ciphertext": token_ciphertext,
            "is_active": True,
            "created_at": created_at,
            "expires_at": expires_at,
            "updated_at": created_at,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def deactivate_expired_for_client(
        self, client_id: str, *, now: datetime | None = None
    ):
        if not ObjectId.is_valid(client_id):
            return None
        now = now or _utc_now()
        return await self.collection.find_one_and_update(
            {
                "client_id": ObjectId(client_id),
                "is_active": True,
                "expires_at": {"$lte": now},
            },
            {"$set": {"is_active": False, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )

    async def deactivate_legacy_for_client(
        self, client_id: str, *, now: datetime | None = None
    ):
        """Invalidate old plaintext-token records without reading their token."""
        if not ObjectId.is_valid(client_id):
            return None
        now = now or _utc_now()
        return await self.collection.find_one_and_update(
            {
                "client_id": ObjectId(client_id),
                "is_active": True,
                "$or": [
                    {"token_hash": {"$exists": False}},
                    {"token_ciphertext": {"$exists": False}},
                ],
            },
            {"$set": {"is_active": False, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )

    async def deactivate_by_id(
        self, token_id: ObjectId, *, now: datetime | None = None
    ):
        if not isinstance(token_id, ObjectId):
            return None
        now = now or _utc_now()
        return await self.collection.find_one_and_update(
            {"_id": token_id, "is_active": True},
            {"$set": {"is_active": False, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
