from datetime import datetime, timezone
from bson import ObjectId
from pymongo import ReturnDocument


class ClientRepository:

    def __init__(self, database):
        self.collection = database["clients"]


    async def get_client_by_id(self, client_id: str):
        if not ObjectId.is_valid(client_id):
            return None
    
        return await self.collection.find_one({
            "_id": ObjectId(client_id)
        })     


    async def create_client(
        self,
        name: str,
        code: str
    ):
        now = datetime.now(timezone.utc)

        client = {
            "name": name,
            "code": code,
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }

        result = await self.collection.insert_one(client)

        client["_id"] = result.inserted_id

        return client


    async def get_by_code(self, code: str):
        return await self.collection.find_one({
            "code": code
        })

    async def get_all_clients(self):
        clients = []

        get_all_client = self.collection.find({}).sort("created_at", -1)

        async for client in get_all_client:
            clients.append(client)

        return clients

    async def update_client(self, client_id: ObjectId, updates: dict):
        """Update mutable client fields and return the resulting document."""
        allowed_updates = {
            key: value
            for key, value in updates.items()
            if key in {"name", "is_active"}
        }
        if not allowed_updates:
            return await self.collection.find_one({"_id": client_id})

        allowed_updates["updated_at"] = datetime.now(timezone.utc)
        return await self.collection.find_one_and_update(
            {"_id": client_id},
            {"$set": allowed_updates},
            return_document=ReturnDocument.AFTER
        )

    async def count_clients(self):
        return await self.collection.count_documents({})

    async def get_clients_by_ids(self, client_ids: list[str]):
        object_ids = [
            ObjectId(client_id)
            for client_id in client_ids
            if ObjectId.is_valid(client_id)
        ]
        if not object_ids:
            return []

        clients = []
        async for client in self.collection.find({"_id": {"$in": object_ids}}):
            clients.append(client)
        return clients


    
