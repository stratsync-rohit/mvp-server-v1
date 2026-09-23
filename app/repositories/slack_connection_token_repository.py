from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument


class SlackConnectionTokenRepository:
    """Persistence for reusable, client-scoped Slack connection tokens."""

    def __init__(self, database):
        self.collection = database["slack_connection_tokens"]

    async def get_active_by_token(self, token: str):
        if not isinstance(token, str) or not token:
            return None
        return await self.collection.find_one({"token": token, "is_active": True})

    async def get_active_by_client_id(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            return None
        return await self.collection.find_one(
            {"client_id": ObjectId(client_id), "is_active": True}
        )

    async def create(self, token: str, client_id: str):
        now = datetime.now(timezone.utc)
        document = {
            "token": token,
            "client_id": ObjectId(client_id),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def deactivate_for_client(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            return None
        return await self.collection.find_one_and_update(
            {"client_id": ObjectId(client_id), "is_active": True},
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
