"""
MongoDB connection management using Motor (async PyMongo driver).

Exposes a single AsyncIOMotorDatabase instance shared across the app via
FastAPI's lifespan, plus helpers to create indexes on startup.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING
from pymongo.errors import PyMongoError

from app.config import get_settings

logger = logging.getLogger("app.database")


class Database:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


db_wrapper = Database()


def get_database() -> AsyncIOMotorDatabase:
    """Dependency-friendly accessor for the shared database instance."""
    if db_wrapper.db is None:
        raise RuntimeError("Database has not been initialized yet")
    return db_wrapper.db


async def connect_to_mongo() -> None:
    settings = get_settings()
    logger.info("connecting_to_mongo", extra={"database": settings.mongodb_database})
    db_wrapper.client = AsyncIOMotorClient(settings.mongodb_uri)
    db_wrapper.db = db_wrapper.client[settings.mongodb_database]

    # Fail fast if Mongo is unreachable.
    await db_wrapper.client.admin.command("ping")
    await ensure_indexes(db_wrapper.db)
    logger.info("mongo_connected")


async def close_mongo_connection() -> None:
    if db_wrapper.client is not None:
        db_wrapper.client.close()
        logger.info("mongo_connection_closed")


async def ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    """
    Create all required indexes. Safe to call on every startup - Mongo
    no-ops if an equivalent index already exists.
    """
    try:
        # Clients: unique code
        await database["clients"].create_index(
            [("code", ASCENDING)], unique=True, name="uniq_client_code"
        )

        await database["industries"].create_index(
            [("slug", ASCENDING)], unique=True, name="uniq_industry_slug"
        )
        await database["industries"].create_index(
            [("is_active", ASCENDING), ("name", ASCENDING)],
            name="idx_active_industry_name",
        )

        # Teams channels:
        # - prevent duplicate active webhook URLs
        # - prevent duplicate active tenant/team/channel combos per client
        await database["teams_channels"].create_index(
            [("client_id", ASCENDING)], name="idx_teams_channels_client_id"
        )
        await database["teams_channels"].create_index(
            [("teams_webhook_url", ASCENDING), ("is_active", ASCENDING)],
            name="idx_webhook_active",
        )
        await database["teams_channels"].create_index(
            [
                ("client_id", ASCENDING),
                ("tenant_id", ASCENDING),
                ("team_id", ASCENDING),
                ("channel_id", ASCENDING),
                ("is_active", ASCENDING),
            ],
            name="idx_client_tenant_team_channel_active",
        )
        await database["slack_destinations"].create_index(
            [("client_id", ASCENDING)], name="idx_slack_destinations_client_id"
        )
        slack_destinations = database["slack_destinations"]
        legacy_slack_partial_filter = {
            "is_active": True,
            "client_id": {"$exists": True},
            "workspace_domain": {"$exists": True},
        }
        existing_slack_indexes = await slack_destinations.index_information()
        existing_legacy_index = existing_slack_indexes.get(
            "uniq_active_slack_destination_identity"
        )
        if (
            existing_legacy_index is not None
            and existing_legacy_index.get("partialFilterExpression")
            != legacy_slack_partial_filter
        ):
            # The old index matched OAuth records with nullable client fields.
            # It is safe to replace because this only changes index coverage;
            # the new OAuth-specific unique index below protects those records.
            await slack_destinations.drop_index(
                "uniq_active_slack_destination_identity"
            )

        await slack_destinations.create_index(
            [
                ("client_id", ASCENDING),
                ("workspace_domain", ASCENDING),
                ("channel_id", ASCENDING),
            ],
            unique=True,
            partialFilterExpression=legacy_slack_partial_filter,
            name="uniq_active_slack_destination_identity",
        )
        oauth_destination_index_name = "uniq_slack_destination_workspace_channel"
        existing_oauth_index = existing_slack_indexes.get(
            oauth_destination_index_name
        )
        oauth_destination_key = [
            ("workspace_id", ASCENDING),
            ("channel_id", ASCENDING),
        ]
        if (
            existing_oauth_index is not None
            and existing_oauth_index.get("key") != oauth_destination_key
        ):
            await slack_destinations.drop_index(oauth_destination_index_name)

        await slack_destinations.create_index(
            oauth_destination_key,
            unique=True,
            partialFilterExpression={
                "workspace_id": {"$exists": True},
                "channel_id": {"$exists": True},
            },
            name="uniq_slack_destination_workspace_channel",
        )
        await database["slack_connection_tokens"].create_index(
            [("token", ASCENDING)],
            unique=True,
            name="uniq_slack_connection_token",
        )
        await database["slack_connection_tokens"].create_index(
            [("client_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"is_active": True},
            name="uniq_active_slack_connection_token_client",
        )
        await database["slack_oauth_states"].create_index(
            [("state", ASCENDING)],
            unique=True,
            name="uniq_slack_oauth_state",
        )
        await database["slack_oauth_states"].create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_slack_oauth_state",
        )
        await database["slack_workspace_installations"].create_index(
            [("slack_team_id", ASCENDING)],
            unique=True,
            name="uniq_slack_workspace_installation_team_id",
        )
        await database["risks"].create_index(
            [("risk_id", ASCENDING)], unique=True, name="uniq_risk_id"
        )
        await database["risks"].create_index(
            [("is_active", ASCENDING), ("industry", ASCENDING)],
            name="idx_active_risk_industry",
        )
        await database["risks"].create_index(
            [
                ("is_active", ASCENDING),
                ("industry_slug", ASCENDING),
                ("created_at", ASCENDING),
            ],
            name="idx_active_risk_industry_slug_created",
        )
        await database["risks"].create_index(
            [("is_active", ASCENDING), ("severity", ASCENDING)],
            name="idx_active_risk_severity",
        )
        await database["notifications"].create_index(
            [("created_at", ASCENDING)],
            name="idx_notification_created_at",
        )
        await database["notifications"].create_index(
            [
                ("client_id", ASCENDING),
                ("destination_id", ASCENDING),
                ("risk_id", ASCENDING),
                ("status", ASCENDING),
            ],
            name="idx_notification_filters",
        )
        await database["notification_guards"].create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_notification_guard",
        )
        logger.info("indexes_ensured")
    except PyMongoError:
        logger.exception("index_creation_failed")
        raise
