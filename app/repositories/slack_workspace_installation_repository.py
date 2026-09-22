from datetime import datetime, timezone

from pymongo import ReturnDocument


class SlackWorkspaceInstallationRepository:
    """Persistence for Slack app installations, keyed by Slack team ID."""

    def __init__(self, database):
        self.collection = database["slack_workspace_installations"]

    async def upsert_installation(
        self,
        installation: dict,
        client_id=None,
    ):
        slack_team_id = installation["slack_team_id"]
        now = datetime.now(timezone.utc)

        updates = {
            key: value
            for key, value in installation.items()
            if key not in {"_id", "created_at", "updated_at", "client_id"}
        }

        # A future trusted state flow may pass a client association. When it
        # does not, leave an existing association untouched on reinstall.
        if client_id is not None:
            updates["client_id"] = client_id

        result = await self.collection.find_one_and_update(
            {"slack_team_id": slack_team_id},
            {
                "$set": {
                    **updates,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "client_id": client_id,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        return result

    async def get_by_id(self, installation_id: str):
        from bson import ObjectId

        if not ObjectId.is_valid(installation_id):
            return None

        return await self.collection.find_one({"_id": ObjectId(installation_id)})

    async def get_by_team_id(self, slack_team_id: str):
        if not slack_team_id:
            return None

        return await self.collection.find_one({"slack_team_id": slack_team_id})
