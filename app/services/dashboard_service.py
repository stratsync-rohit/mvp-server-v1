import asyncio


class DashboardService:

    def __init__(
        self,
        client_repository,
        teams_channel_repository,
        notification_repository
    ):
        self.client_repository = client_repository
        self.teams_channel_repository = teams_channel_repository
        self.notification_repository = notification_repository

    async def get_summary(self, client_id: str | None = None):
        if client_id:
            client = await self.client_repository.get_client_by_id(client_id)
            if client is None:
                raise ValueError("Client not found")

            (
                active_teams,
                active_teams_channels,
                inactive_channels,
                notifications_sent
            ) = await asyncio.gather(
                self.teams_channel_repository.count_active_teams_by_client(client_id),
                self.teams_channel_repository.count_active_channels_by_client(client_id),
                self.teams_channel_repository.count_inactive_channels_by_client(client_id),
                self.notification_repository.count_sent_notifications_by_client(client_id)
            )

            return {
                "client": {
                    "id": str(client["_id"]),
                    "name": client["name"],
                    "code": client["code"],
                    "is_active": client.get("is_active", True)
                },
                "active_teams": active_teams,
                "active_teams_channels": active_teams_channels,
                "inactive_channels": inactive_channels,
                "notifications_sent": notifications_sent
            }

        (
            total_clients,
            active_teams_channels,
            inactive_channels,
            notifications_sent
        ) = await asyncio.gather(
            self.client_repository.count_clients(),
            self.teams_channel_repository.count_active_channels(),
            self.teams_channel_repository.count_inactive_channels(),
            self.notification_repository.count_sent_notifications()
        )

        return {
            "total_clients": total_clients,
            "active_teams_channels": active_teams_channels,
            "inactive_channels": inactive_channels,
            "notifications_sent": notifications_sent
        }

    async def get_recent_integrations(self, limit: int = 5):
        channels = await self.teams_channel_repository.get_recent_channels(limit)
        channels = [channel for channel in channels if channel.get("client_id")]
        client_ids = {
            str(channel["client_id"])
            for channel in channels
            if channel.get("client_id")
        }
        clients = await self.client_repository.get_clients_by_ids(
            list(client_ids)
        )
        client_names = {
            str(client["_id"]): client["name"]
            for client in clients
            if client is not None
        }

        return [
            {
                "id": str(channel["_id"]),
                "client_id": str(channel["client_id"]),
                "client_name": client_names.get(str(channel["client_id"]), "Unknown client"),
                "team_name": channel.get("team_name") or "Unnamed Team",
                "channel_name": channel.get("channel_name"),
                "is_active": channel.get("is_active", True),
                "webhook_configured": bool(channel.get("teams_webhook_url")),
                "created_at": channel.get("created_at")
            }
            for channel in channels
        ]
