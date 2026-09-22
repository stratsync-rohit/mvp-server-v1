from datetime import datetime, timezone

from pymongo import ReturnDocument


class RiskDestinationOverrideRepository:

    def __init__(self, database):
        self.collection = database["risk_destination_overrides"]

    async def get_by_risk_and_destination(
        self,
        risk_id: str,
        destination_id: str,
        is_active: bool | None = True,
    ):
        query = {
            "risk_id": risk_id,
            "destination_id": destination_id,
        }

        if is_active is not None:
            query["is_active"] = is_active

        return await self.collection.find_one(query)

    async def create_override(self, document: dict):
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def upsert_override(
        self,
        risk_id: str,
        destination_id: str,
        document: dict,
    ):
        now = datetime.now(timezone.utc)

        update_document = dict(document)

        # These values always come from the method arguments.
        update_document["risk_id"] = risk_id
        update_document["destination_id"] = destination_id
        update_document["updated_at"] = now

        return await self.collection.find_one_and_update(
            {
                "risk_id": risk_id,
                "destination_id": destination_id,
            },
            {
                "$set": update_document,
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def disable_override(
        self,
        risk_id: str,
        destination_id: str,
    ):
        return await self.collection.find_one_and_update(
            {
                "risk_id": risk_id,
                "destination_id": destination_id,
            },
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def delete_override(
        self,
        risk_id: str,
        destination_id: str,
    ) -> bool:
        result = await self.collection.delete_one(
            {
                "risk_id": risk_id,
                "destination_id": destination_id,
            }
        )

        return result.deleted_count == 1

    async def get_overrides_by_risk(
        self,
        risk_id: str,
        is_active: bool | None = True,
    ):
        query = {
            "risk_id": risk_id,
        }

        if is_active is not None:
            query["is_active"] = is_active

        overrides = []

        cursor = self.collection.find(query).sort([
            ("created_at", -1),
            ("_id", -1),
        ])

        async for override in cursor:
            overrides.append(override)

        return overrides