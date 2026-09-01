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
        await database["slack_destinations"].create_index(
            [
                ("client_id", ASCENDING),
                ("workspace_domain", ASCENDING),
                ("channel_id", ASCENDING),
            ],
            unique=True,
            partialFilterExpression={"is_active": True},
            name="uniq_active_slack_destination_identity",
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
