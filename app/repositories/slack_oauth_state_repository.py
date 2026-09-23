from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument


class SlackOAuthStateRepository:
    """Persistence for short-lived, one-time Slack OAuth states."""

    def __init__(self, database):
        self.collection = database["slack_oauth_states"]

    async def create(
        self,
        state: str,
        client_id: str,
        connection_token_id,
        expires_at: datetime,
    ):
        now = datetime.now(timezone.utc)
        document = {
            "state": state,
            "client_id": ObjectId(client_id),
            "connection_token_id": connection_token_id,
            "expires_at": expires_at,
            "used": False,
            "created_at": now,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def get_by_state(self, state: str):
        if not isinstance(state, str) or not state:
            return None
        return await self.collection.find_one({"state": state})

    async def mark_used(self, state: str):
        return await self.collection.find_one_and_update(
            {"state": state, "used": False},
            {
                "$set": {
                    "used": True,
                    "used_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
