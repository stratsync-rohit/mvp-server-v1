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

        result = await self.collection.find_one_and_update(
            {"slack_team_id": slack_team_id},
            {
                "$set": {
                    **updates,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
                # Remove data written by earlier OAuth flows. The workspace
                # installation is intentionally not client-owned.
                "$unset": {
                    "incoming_webhook": "",
                    "client_id": "",
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
