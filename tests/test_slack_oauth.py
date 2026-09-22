from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.dependencies import get_slack_oauth_service
from app.main import app
from app.schemas.slack_workspace_installation import (
    SlackIncomingWebhookMetadata,
    SlackWorkspaceInstallation,
)


pytestmark = pytest.mark.asyncio


def _installation(
    workspace_id: str,
    workspace_name: str,
    channel_id: str,
    channel_name: str,
    webhook_suffix: str,
):
    return SlackWorkspaceInstallation(
        slack_team_id=workspace_id,
        slack_team_name=workspace_name,
        enterprise_id=None,
        app_id="A123456",
        bot_user_id="U123456",
        access_token=f"xoxb-private-{webhook_suffix}",
        token_type="bot",
        scope="incoming-webhook,chat:write",
        is_enterprise_install=False,
        incoming_webhook=SlackIncomingWebhookMetadata(
            channel=channel_name,
            channel_id=channel_id,
            configuration_url=(
                f"https://slack.com/apps/configure/{webhook_suffix}"
            ),
            url=(
                "https://hooks.slack.com/services/"
                f"T/B/{webhook_suffix}"
            ),
        ),
    )


async def _connect(client, oauth_service, installation):
    oauth_service.exchange_code.return_value = installation
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    return await client.get("/api/slack/oauth/callback?code=test-code")


async def test_first_oauth_channel_creates_workspace_and_destination(
    client,
    mongo_db,
    caplog,
):
    oauth_service = AsyncMock()
    response = await _connect(
        client,
        oauth_service,
        _installation(
            "T0C3D4N42MT",
            "RC Orbital Operations",
            "C0C32Q6U1JB",
            "#supply-chain-risk",
            "first",
        ),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["destination_id"]
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 1

    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    destination = await mongo_db["slack_destinations"].find_one({})
    assert "incoming_webhook" not in workspace
    assert destination["workspace_id"] == "T0C3D4N42MT"
    assert destination["channel_id"] == "C0C32Q6U1JB"
    assert "xoxb-private-first" not in response.text
    assert "hooks.slack.com" not in response.text
    assert "slack.com/apps/configure/first" not in response.text
    assert "xoxb-private-first" not in caplog.text
    assert "hooks.slack.com" not in caplog.text


async def test_second_channel_same_workspace_creates_destination_only(
    client,
    mongo_db,
):
    oauth_service = AsyncMock()
    first = _installation(
        "T0C3D4N42MT",
        "RC Orbital Operations",
        "C0C32Q6U1JB",
        "#supply-chain-risk",
        "first",
    )
    second = _installation(
        "T0C3D4N42MT",
        "RC Orbital Operations",
        "C0C3G760GKY",
        "#inventory-alerts",
        "second",
    )

    first_response = await _connect(client, oauth_service, first)
    first_installation_id = first_response.json()["data"]["installation_id"]
    second_response = await _connect(client, oauth_service, second)

    assert second_response.status_code == 200
    assert (
        second_response.json()["data"]["installation_id"]
        == first_installation_id
    )
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 2


async def test_reconnecting_same_channel_updates_and_reactivates_destination(
    client,
    mongo_db,
):
    oauth_service = AsyncMock()
    first = _installation(
        "T0C3D4N42MT",
        "RC Orbital Operations",
        "C0C32Q6U1JB",
        "#supply-chain-risk",
        "first",
    )
    second = _installation(
        "T0C3D4N42MT",
        "RC Orbital Operations",
        "C0C32Q6U1JB",
        "#supply-chain-risk-renamed",
        "replacement",
    )

    await _connect(client, oauth_service, first)
    original = await mongo_db["slack_destinations"].find_one({})
    original_created_at = original["created_at"]
    await mongo_db["slack_destinations"].update_one(
        {"_id": original["_id"]},
        {
            "$set": {
                "is_active": False,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    response = await _connect(client, oauth_service, second)
    assert response.status_code == 200
    assert response.json()["data"]["destination_id"] == str(original["_id"])
    assert await mongo_db["slack_destinations"].count_documents({}) == 1

    updated = await mongo_db["slack_destinations"].find_one({})
    assert updated["is_active"] is True
    assert updated["channel_name"] == "#supply-chain-risk-renamed"
    assert updated["webhook_url"].endswith("replacement")
    assert updated["created_at"] == original_created_at


async def test_different_workspace_creates_installation_and_destination(
    client,
    mongo_db,
):
    oauth_service = AsyncMock()
    await _connect(
        client,
        oauth_service,
        _installation(
            "T0C3D4N42MT",
            "RC Orbital Operations",
            "C0C32Q6U1JB",
            "#supply-chain-risk",
            "first",
        ),
    )
    response = await _connect(
        client,
        oauth_service,
        _installation(
            "T0OTHERWORKSPACE",
            "Another Workspace",
            # Channel IDs are workspace-scoped, so this also verifies that
            # workspace_id participates in the destination identity.
            "C0C32Q6U1JB",
            "#other-alerts",
            "other",
        ),
    )

    assert response.status_code == 200
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 2
    assert await mongo_db["slack_destinations"].count_documents({}) == 2


async def test_oauth_indexes_exist(mongo_db):
    installation_indexes = await mongo_db[
        "slack_workspace_installations"
    ].index_information()
    assert installation_indexes[
        "uniq_slack_workspace_installation_team_id"
    ]["unique"] is True

    destination_indexes = await mongo_db["slack_destinations"].index_information()
    destination_index = destination_indexes[
        "uniq_slack_destination_workspace_channel"
    ]
    assert destination_index["unique"] is True
    assert destination_index["key"] == [
        ("workspace_id", 1),
        ("channel_id", 1),
    ]
