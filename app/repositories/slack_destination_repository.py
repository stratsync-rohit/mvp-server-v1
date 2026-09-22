from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument


class SlackDestinationRepository:

    def __init__(self, database):
        self.collection = database["slack_destinations"]


    async def upsert_oauth_destination(
        self,
        workspace_id: str,
        workspace_name: str,
        channel_id: str,
        channel_name: str,
        webhook_url: str,
        configuration_url: str | None = None,
        client_id=None,
    ):
        """Upsert one OAuth destination by client/workspace/channel."""
        now = datetime.now(timezone.utc)
        updates = {
            "client_id": client_id,
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "webhook_url": webhook_url,
            "configuration_url": configuration_url,
            "is_active": True,
            "updated_at": now,
        }

        identity = {
            "client_id": client_id,
            "workspace_id": workspace_id,
            "channel_id": channel_id,
        }
        return await self.collection.find_one_and_update(
            identity,
            {
                "$set": updates,
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )


    async def create_destination(
        self,
        client_id: str,
        member_name: str,
        workspace_domain: str,
        channel_id: str,
        channel_name: str,
        channel_link: str,
        webhook_url: str,
    ):
        now = datetime.now(timezone.utc)

        destination = {
            "client_id": ObjectId(client_id),

            "member_name": member_name,

            "workspace_domain": workspace_domain,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "channel_link": channel_link,

            "webhook_url": webhook_url,

            "is_active": True,

            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(destination)

        destination["_id"] = result.inserted_id

        return destination


    async def get_by_id(self, destination_id: str):

        if not ObjectId.is_valid(destination_id):
            return None

        return await self.collection.find_one({
            "_id": ObjectId(destination_id)
        })


    async def get_destinations_by_client(self, client_id: str):

        if not ObjectId.is_valid(client_id):
            return []

        destinations = []

        cursor = (
            self.collection
            .find({
                "client_id": ObjectId(client_id)
            })
            .sort("created_at", -1)
        )

        async for destination in cursor:
            destinations.append(destination)

        return destinations


    async def get_active_by_identity(
        self,
        client_id: str,
        workspace_domain: str,
        channel_id: str,
        exclude_destination_id: str | None = None,
    ):

        if not ObjectId.is_valid(client_id):
            return None

        query = {
            "client_id": ObjectId(client_id),
            "workspace_domain": workspace_domain,
            "channel_id": channel_id,
            "is_active": True,
        }

        if (
            exclude_destination_id
            and ObjectId.is_valid(exclude_destination_id)
        ):
            query["_id"] = {
                "$ne": ObjectId(exclude_destination_id)
            }

        return await self.collection.find_one(query)


    async def get_active_oauth_by_identity(
        self,
        client_id: str,
        workspace_id: str,
        channel_id: str,
        exclude_destination_id: str | None = None,
    ):
        if not ObjectId.is_valid(client_id):
            return None

        query = {
            "client_id": ObjectId(client_id),
            "workspace_id": workspace_id,
            "channel_id": channel_id,
            "is_active": True,
        }
        if (
            exclude_destination_id
            and ObjectId.is_valid(exclude_destination_id)
        ):
            query["_id"] = {"$ne": ObjectId(exclude_destination_id)}

        return await self.collection.find_one(query)


    async def update_destination(
        self,
        destination_id: str,
        update_data: dict
    ):

        if not ObjectId.is_valid(destination_id):
            return None

        allowed_fields = {
            "member_name",
            "workspace_domain",
            "channel_id",
            "channel_name",
            "channel_link",
            "webhook_url",
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
            {
                "_id": ObjectId(destination_id)
            },
            {
                "$set": updates
            },
            return_document=ReturnDocument.AFTER,
        )


    async def soft_delete(self, destination_id: str):

        return await self.update_destination(
            destination_id,
            {
                "is_active": False
            }
        )
