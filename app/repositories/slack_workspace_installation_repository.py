from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.exceptions import ConflictError


class SlackWorkspaceInstallationRepository:
    """Persistence for Slack app installations, keyed by Slack team ID."""

    def __init__(self, database):
        self.collection = database["slack_workspace_installations"]

    async def upsert_installation(
        self,
        installation: dict,
        client_id: ObjectId,
    ):
        if not isinstance(client_id, ObjectId):
            raise ValueError("Invalid client ownership")

        slack_team_id = installation["slack_team_id"]
        now = datetime.now(timezone.utc)

        updates = {
            key: value
            for key, value in installation.items()
            if key not in {
                "_id",
                "created_at",
                "updated_at",
                "client_id",
                # Channel-specific webhook metadata belongs in
                # slack_destinations, never in the workspace record.
                "incoming_webhook",
            }
        }

        query = {
            "slack_team_id": slack_team_id,
            "$or": [
                {"client_id": client_id},
                {"client_id": str(client_id)},
                {"client_id": None},
                {"client_id": {"$exists": False}},
            ],
        }
        update = {
            "$set": {
                **updates,
                "client_id": client_id,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
            # Channel-specific webhook metadata belongs in
            # slack_destinations, never in the workspace record.
            "$unset": {"incoming_webhook": ""},
        }

        try:
            result = await self.collection.find_one_and_update(
                query,
                update,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            existing = await self.get_by_team_id(slack_team_id)
            if existing is not None:
                raise ConflictError(
                    "This Slack workspace is already connected to another "
                    "StratSync client."
                ) from exc
            raise

        if result is not None:
            return result

        existing = await self.get_by_team_id(slack_team_id)
        if existing is not None:
            raise ConflictError(
                "This Slack workspace is already connected to another "
                "StratSync client."
            )

        raise RuntimeError("Unable to persist Slack workspace installation")

    async def get_by_id(self, installation_id: str):
        from bson import ObjectId

        if not ObjectId.is_valid(installation_id):
            return None

        return await self.collection.find_one({"_id": ObjectId(installation_id)})

    async def get_by_team_id(self, slack_team_id: str):
        if not slack_team_id:
            return None

        return await self.collection.find_one({"slack_team_id": slack_team_id})
