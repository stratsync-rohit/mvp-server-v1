from datetime import datetime, timedelta, timezone
from hashlib import sha256

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class NotificationRepository:

    DUPLICATE_WINDOW_SECONDS = 5

    def __init__(self, database):
        self.collection = database["notifications"]
        self.guard_collection = database["notification_guards"]

    async def acquire_duplicate_guard(
        self,
        risk_id: str,
        destination_id: str
    ) -> bool:
        now = datetime.now(timezone.utc)
        guard_id = sha256(
            f"{risk_id}\0{destination_id}".encode("utf-8")
        ).hexdigest()

        try:
            await self.guard_collection.find_one_and_update(
                {
                    "_id": guard_id,
                    "$or": [
                        {"expires_at": {"$lte": now}},
                        {"expires_at": {"$exists": False}}
                    ]
                },
                {
                    "$set": {
                        "expires_at": now + timedelta(
                            seconds=self.DUPLICATE_WINDOW_SECONDS
                        ),
                        "updated_at": now
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            return False

        return True

    async def create_notification(self, notification: dict):
        document = dict(notification)
        document["created_at"] = datetime.now(timezone.utc)
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def mark_sent(self, notification_id: ObjectId):
        sent_at = datetime.now(timezone.utc)
        return await self.collection.find_one_and_update(
            {"_id": notification_id},
            {
                "$set": {
                    "status": "sent",
                    "sent_at": sent_at
                },
                "$unset": {"failure_reason": ""}
            },
            return_document=ReturnDocument.AFTER
        )

    async def mark_failed(
        self,
        notification_id: ObjectId,
        failure_reason: str
    ):
        return await self.collection.find_one_and_update(
            {"_id": notification_id},
            {
                "$set": {
                    "status": "failed",
                    "failure_reason": failure_reason
                }
            },
            return_document=ReturnDocument.AFTER
        )

    async def get_notifications(
        self,
        client_id: str | None = None,
        risk_id: str | None = None,
        status: str | None = None,
        destination_id: str | None = None
    ):
        query = {}

        if client_id:
            if not ObjectId.is_valid(client_id):
                return []
            query["client_id"] = ObjectId(client_id)

        if risk_id:
            query["risk_id"] = risk_id

        if status:
            query["status"] = status

        if destination_id:
            if not ObjectId.is_valid(destination_id):
                return []
            query["destination_id"] = ObjectId(destination_id)

        notifications = []
        cursor = self.collection.find(query).sort([
            ("created_at", -1),
            ("_id", -1)
        ])

        async for notification in cursor:
            notifications.append(notification)

        return notifications

    async def count_sent_notifications(self) -> int:
        return await self.collection.count_documents({
            "status": "sent"
        })

    async def count_sent_notifications_by_client(self, client_id: str) -> int:
        if not ObjectId.is_valid(client_id):
            return 0

        return await self.collection.count_documents({
            "client_id": ObjectId(client_id),
            "status": "sent"
        })
