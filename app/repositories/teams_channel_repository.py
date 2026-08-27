from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument


class TeamsChannelRepository:

    def __init__(self, database):
        self.collection = database["teams_channels"]


    async def create_channel(
        self,
        client_id: str,
        team_name: str,
        channel_url: str,
        teams_webhook_url: str,
        channel_name: str | None = None,
        tenant_id: str | None = None,
        team_id: str | None = None,
        channel_id: str | None = None
    ):
        now = datetime.now(timezone.utc)

        channel = {
            "client_id": ObjectId(client_id),

            "team_name": team_name,
            "channel_name": channel_name,

            "channel_url": channel_url,
            "teams_webhook_url": teams_webhook_url,

            "tenant_id": tenant_id,
            "team_id": team_id,
            "channel_id": channel_id,

            "is_active": True,

            "created_at": now,
            "updated_at": now
        }

        result = await self.collection.insert_one(channel)

        channel["_id"] = result.inserted_id

        return channel


    async def get_by_id(self, destination_id: str):

        if not ObjectId.is_valid(destination_id):
            return None

        return await self.collection.find_one({
            "_id": ObjectId(destination_id)
        })


    async def update_channel(self, destination_id: str, update_data: dict):
        if not ObjectId.is_valid(destination_id):
            return None

        allowed_fields = {
            "team_name",
            "channel_name",
            "channel_url",
            "teams_webhook_url",
            "tenant_id",
            "team_id",
            "channel_id",
            "is_active",
        }
        updates = {
            key: value
            for key, value in update_data.items()
            if key in allowed_fields
        }
        if not updates:
            return await self.get_by_id(destination_id)

        updates["updated_at"] = datetime.now(timezone.utc)
        return await self.collection.find_one_and_update(
            {"_id": ObjectId(destination_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )


    async def get_by_webhook_url(self, webhook_url: str):

        return await self.collection.find_one({
            "teams_webhook_url": webhook_url,
            "is_active": True
        })


    async def get_channels_by_client(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            return []

        channels = []

        cursor = self.collection.find({
            "client_id": ObjectId(client_id)
        }).sort("created_at", -1)

        async for channel in cursor:
            channels.append(channel)

        return channels

    async def get_by_teams_identity(
        self,
        client_id: str,
        tenant_id: str,
        team_id: str,
        channel_id: str
    ):

        if not ObjectId.is_valid(client_id):
            return None

        return await self.collection.find_one({
            "client_id": ObjectId(client_id),
            "tenant_id": tenant_id,
            "team_id": team_id,
            "channel_id": channel_id
        })


    async def find_by_client_and_team_id(
        self,
        client_id: str,
        team_id: str
    ):
        if not ObjectId.is_valid(client_id) or not team_id:
            return None

        return await self.collection.find_one({
            "client_id": ObjectId(client_id),
            "team_id": team_id
        })


    async def update_team_name(
        self,
        client_id: str,
        team_id: str,
        team_name: str
    ):
        if not ObjectId.is_valid(client_id) or not team_id:
            return 0

        result = await self.collection.update_many(
            {
                "client_id": ObjectId(client_id),
                "team_id": team_id
            },
            {
                "$set": {
                    "team_name": team_name,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        return result.modified_count


    async def count_active_channels(self) -> int:
        return await self.collection.count_documents({
            "is_active": True
        })


    async def count_inactive_channels(self) -> int:
        return await self.collection.count_documents({
            "is_active": False
        })


    async def count_active_channels_by_client(self, client_id: str) -> int:
        if not ObjectId.is_valid(client_id):
            return 0

        return await self.collection.count_documents({
            "client_id": ObjectId(client_id),
            "is_active": True
        })


    async def count_inactive_channels_by_client(self, client_id: str) -> int:
        if not ObjectId.is_valid(client_id):
            return 0

        return await self.collection.count_documents({
            "client_id": ObjectId(client_id),
            "is_active": False
        })


    async def count_active_teams_by_client(self, client_id: str) -> int:
        if not ObjectId.is_valid(client_id):
            return 0

        team_names = await self.collection.distinct(
            "team_name",
            {
                "client_id": ObjectId(client_id),
                "is_active": True
            }
        )
        return len([name for name in team_names if name])


    async def get_recent_channels(self, limit: int = 5):
        channels = []
        cursor = self.collection.find({}).sort("created_at", -1).limit(limit)

        async for channel in cursor:
            channels.append(channel)

        return channels
