"""
Shared pytest fixtures.

Uses mongomock-motor to fully avoid touching a real MongoDB instance, and
overrides the n8n service dependency with an AsyncMock so tests never make
real HTTP calls out to n8n (and therefore never actually notify Teams).
"""
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.database import ensure_indexes
from app.config import Settings
from app.dependencies import (
    get_n8n_service,
    get_slack_interaction_n8n_service,
    get_slack_interaction_service,
    get_slack_n8n_service,
)
from app.main import app
from app.services.slack_interaction_service import SlackInteractionService


TEST_SLACK_SIGNING_SECRET = "test-slack-signing-secret"


@pytest_asyncio.fixture
async def mongo_db():
    client = AsyncMongoMockClient()
    database = client["stratsync_rrm_test"]
    await ensure_indexes(database)
    yield database


@pytest_asyncio.fixture
async def mock_n8n_service():
    service = AsyncMock()
    service.trigger_notification = AsyncMock(return_value={"status": "accepted"})
    return service


@pytest_asyncio.fixture
async def mock_slack_n8n_service():
    service = AsyncMock()
    service.trigger_notification = AsyncMock(return_value={"status": "accepted"})
    return service


@pytest_asyncio.fixture
async def mock_slack_interaction_n8n_service():
    service = AsyncMock()
    service.trigger_notification = AsyncMock(return_value={"status": "accepted"})
    return service


@pytest_asyncio.fixture
async def client(
    mongo_db,
    mock_n8n_service,
    mock_slack_n8n_service,
    mock_slack_interaction_n8n_service,
):
    from app.database import db_wrapper

    db_wrapper.db = mongo_db
    await mongo_db["risks"].insert_one(
        {
            "risk_id": "RSK-21132-0472",
            "title": "Supplier Reliability Risk Detected",
            "industry": "Distribution & Trading",
            "is_active": True,
        }
    )

    app.dependency_overrides[get_n8n_service] = lambda: mock_n8n_service
    app.dependency_overrides[get_slack_n8n_service] = (
        lambda: mock_slack_n8n_service
    )
    app.dependency_overrides[get_slack_interaction_service] = lambda: (
        SlackInteractionService(
            Settings(
                _env_file=None,
                SLACK_SIGNING_SECRET=TEST_SLACK_SIGNING_SECRET,
            )
        )
    )
    app.dependency_overrides[get_slack_interaction_n8n_service] = (
        lambda: mock_slack_interaction_n8n_service
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
    db_wrapper.db = None
