from datetime import datetime, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from bson import ObjectId

from app.config import Settings
from app.dependencies import (
    get_slack_oauth_service,
    get_slack_oauth_state_service,
)
from app.main import app
from app.repositories.client_repository import ClientRepository
from app.repositories.slack_destination_repository import (
    SlackDestinationRepository,
)
from app.schemas.slack_workspace_installation import (
    SlackIncomingWebhookMetadata,
    SlackWorkspaceInstallation,
)
from app.services.slack_oauth_service import SlackOAuthService
from app.services.slack_oauth_state_service import SlackOAuthStateService


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


def _test_settings():
    return Settings.model_construct(
        slack_client_id="A123456",
        slack_client_secret="client-secret",
        slack_oauth_redirect_uri="https://backend.test/api/slack/oauth/callback",
        slack_oauth_scopes="incoming-webhook,chat:write",
        slack_oauth_state_secret="state-secret",
    )


async def _create_client(client, name):
    response = await client.post("/api/clients", json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _connect(client, mongo_db, oauth_service, installation, client_id):
    oauth_service.exchange_code.return_value = installation
    settings = _test_settings()
    state_service = SlackOAuthStateService(
        settings=settings,
        client_repository=ClientRepository(mongo_db),
    )
    real_oauth_service = SlackOAuthService(settings)
    oauth_service.build_authorization_url = (
        real_oauth_service.build_authorization_url
    )
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    app.dependency_overrides[get_slack_oauth_state_service] = (
        lambda: state_service
    )

    start = await client.get(
        "/api/slack/oauth/start",
        params={"client_id": client_id},
        follow_redirects=False,
    )
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    return await client.get(
        "/api/slack/oauth/callback",
        params={"code": "test-code", "state": state},
    )


async def test_first_oauth_channel_creates_workspace_and_destination(
    client,
    mongo_db,
    caplog,
):
    client_id = await _create_client(client, "RC Orbital Operations")
    oauth_service = AsyncMock()
    response = await _connect(
        client, mongo_db, oauth_service,
        _installation(
            "T0C3D4N42MT",
            "RC Orbital Operations",
            "C0C32Q6U1JB",
            "#supply-chain-risk",
            "first",
        ),
        client_id,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["destination_id"]
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 1

    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    destination = await mongo_db["slack_destinations"].find_one({})
    assert "incoming_webhook" not in workspace
    assert "client_id" not in workspace
    assert destination["client_id"] is not None
    assert str(destination["client_id"]) == client_id
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
    client_id = await _create_client(client, "RC Orbital Operations")
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

    first_response = await _connect(
        client, mongo_db, oauth_service, first, client_id
    )
    first_installation_id = first_response.json()["data"]["installation_id"]
    second_response = await _connect(
        client, mongo_db, oauth_service, second, client_id
    )

    assert second_response.status_code == 200
    assert (
        second_response.json()["data"]["installation_id"]
        == first_installation_id
    )
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 2
    listed = await client.get(f"/api/clients/{client_id}/slack/channels")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 2
    assert all(
        item["client_id"] == client_id for item in listed.json()["data"]
    )


async def test_reconnecting_same_channel_updates_and_reactivates_destination(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "RC Orbital Operations")
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

    await _connect(client, mongo_db, oauth_service, first, client_id)
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

    response = await _connect(
        client, mongo_db, oauth_service, second, client_id
    )
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
    client_a_id = await _create_client(client, "RC Orbital Operations")
    client_b_id = await _create_client(client, "Another Client")
    oauth_service = AsyncMock()
    await _connect(
        client, mongo_db, oauth_service,
        _installation(
            "T0C3D4N42MT",
            "RC Orbital Operations",
            "C0C32Q6U1JB",
            "#supply-chain-risk",
            "first",
        ),
        client_a_id,
    )
    response = await _connect(
        client, mongo_db, oauth_service,
        _installation(
            "T0OTHERWORKSPACE",
            "Another Workspace",
            # Channel IDs are workspace-scoped, so this also verifies that
            # workspace_id participates in the destination identity.
            "C0C32Q6U1JB",
            "#other-alerts",
            "other",
        ),
        client_b_id,
    )

    assert response.status_code == 200
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 2
    assert await mongo_db["slack_destinations"].count_documents({}) == 2

    client_a_destinations = await client.get(
        f"/api/clients/{client_a_id}/slack/channels"
    )
    client_b_destinations = await client.get(
        f"/api/clients/{client_b_id}/slack/channels"
    )
    assert len(client_a_destinations.json()["data"]) == 1
    assert len(client_b_destinations.json()["data"]) == 1
    assert client_a_destinations.json()["data"][0]["client_id"] == client_a_id
    assert client_b_destinations.json()["data"][0]["client_id"] == client_b_id


async def test_different_clients_same_workspace_channel_do_not_overwrite(
    client,
    mongo_db,
):
    client_a_id = await _create_client(client, "Client A")
    client_b_id = await _create_client(client, "Client B")
    oauth_service = AsyncMock()
    installation = _installation(
        "T0SHAREDWORKSPACE",
        "Shared Workspace",
        "C0SHAREDCHANNEL",
        "#shared-alerts",
        "shared",
    )

    await _connect(client, mongo_db, oauth_service, installation, client_a_id)
    response = await _connect(
        client, mongo_db, oauth_service, installation, client_b_id
    )

    assert response.status_code == 200
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 2
    client_a_channels = (
        await client.get(f"/api/clients/{client_a_id}/slack/channels")
    ).json()["data"]
    client_b_channels = (
        await client.get(f"/api/clients/{client_b_id}/slack/channels")
    ).json()["data"]
    assert len(client_a_channels) == 1
    assert len(client_b_channels) == 1
    assert client_a_channels[0]["client_id"] == client_a_id
    assert client_b_channels[0]["client_id"] == client_b_id


async def test_tampered_oauth_state_is_rejected_before_code_exchange(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "State Client")
    oauth_service = AsyncMock()
    settings = _test_settings()
    state_service = SlackOAuthStateService(
        settings=settings,
        client_repository=ClientRepository(mongo_db),
    )
    oauth_service.build_authorization_url = (
        SlackOAuthService(settings).build_authorization_url
    )
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    app.dependency_overrides[get_slack_oauth_state_service] = (
        lambda: state_service
    )

    start = await client.get(
        "/api/slack/oauth/start",
        params={"client_id": client_id},
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    tampered_state = f"{state[:-1]}{'A' if state[-1] != 'A' else 'B'}"

    response = await client.get(
        "/api/slack/oauth/callback",
        params={"code": "test-code", "state": tampered_state},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired Slack OAuth state"}
    oauth_service.exchange_code.assert_not_awaited()


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
        ("client_id", 1),
        ("workspace_id", 1),
        ("channel_id", 1),
    ]


async def test_oauth_destination_upsert_has_no_conflicting_update_paths(
    mongo_db,
):
    repository = SlackDestinationRepository(mongo_db)
    client_id = ObjectId()

    first = await repository.upsert_oauth_destination(
        client_id=client_id,
        workspace_id="T-CONFLICT-CHECK",
        workspace_name="Conflict Check Workspace",
        channel_id="C-CONFLICT-CHECK",
        channel_name="#first",
        webhook_url="https://hooks.slack.com/services/T/B/first",
        configuration_url="https://slack.com/configure/first",
    )
    second = await repository.upsert_oauth_destination(
        client_id=client_id,
        workspace_id="T-CONFLICT-CHECK",
        workspace_name="Conflict Check Workspace",
        channel_id="C-CONFLICT-CHECK",
        channel_name="#updated",
        webhook_url="https://hooks.slack.com/services/T/B/updated",
        configuration_url="https://slack.com/configure/updated",
    )

    assert first["_id"] == second["_id"]
    assert second["client_id"] == client_id
    assert second["channel_name"] == "#updated"
    assert await mongo_db["slack_destinations"].count_documents({}) == 1
