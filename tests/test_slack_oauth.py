import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from bson import ObjectId

from app.config import Settings
from app.api import client as client_api
from app.dependencies import (
    get_slack_oauth_service,
    get_slack_oauth_state_service,
    get_slack_workspace_installation_service,
)
from app.main import app
from app.exceptions import (
    ConflictError,
    SlackConnectionTokenConfigurationError,
    SlackOAuthResponseError,
)
from app.repositories.client_repository import ClientRepository
from app.repositories.slack_destination_repository import (
    SlackDestinationRepository,
)
from app.repositories.slack_connection_token_repository import (
    SlackConnectionTokenRepository,
)
from app.repositories.slack_oauth_state_repository import (
    SlackOAuthStateRepository,
)
from app.schemas.slack_workspace_installation import (
    SlackIncomingWebhookMetadata,
    SlackWorkspaceInstallation,
)
from app.services.slack_oauth_service import SlackOAuthService
from app.services.slack_oauth_state_service import SlackOAuthStateService
from app.services.slack_connection_token_service import SlackConnectionTokenService


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


async def _connect(
    client,
    mongo_db,
    oauth_service,
    installation,
    client_id,
):
    oauth_service.exchange_code.return_value = installation
    settings = _test_settings()
    state_service = SlackOAuthStateService(
        settings=settings,
        client_repository=ClientRepository(mongo_db),
        repository=SlackOAuthStateRepository(mongo_db),
    )
    real_oauth_service = SlackOAuthService(settings)
    oauth_service.build_authorization_url = (
        real_oauth_service.build_authorization_url
    )
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    app.dependency_overrides[get_slack_oauth_state_service] = (
        lambda: state_service
    )

    connect_url_response = await client.get(
        f"/api/clients/{client_id}/slack/connect-url",
    )
    assert connect_url_response.status_code == 200
    connect_url = connect_url_response.json()["data"]["connect_url"]
    token = parse_qs(urlparse(connect_url).query)["token"][0]

    start = await client.get(
        "/api/slack/oauth/start",
        params={"token": token},
        follow_redirects=False,
    )
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    return await client.get(
        "/api/slack/oauth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )


async def test_oauth_callback_returns_clean_success_html(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Redirect Client")
    oauth_service = AsyncMock()
    installation = _installation(
        "T-REDIRECT-CLIENT",
        "Redirect <Workspace>",
        "C-REDIRECT-CHANNEL",
        "#redirects & alerts",
        "redirect",
    )
    response = await _connect(
        client,
        mongo_db,
        oauth_service,
        installation,
        client_id,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Slack Connected Successfully" in response.text
    assert "oauth-card" in response.text
    assert "oauth-icon success" in response.text
    assert (
        "Your Slack workspace and channel are now connected to StratSync."
        in response.text
    )
    assert '<span class="oauth-detail-label">Workspace</span>' in response.text
    assert (
        '<span class="oauth-detail-value">Redirect &lt;Workspace&gt;</span>'
        in response.text
    )
    assert '<span class="oauth-detail-label">Channel</span>' in response.text
    assert (
        '<span class="oauth-detail-value">#redirects &amp; alerts</span>'
        in response.text
    )
    assert "<Workspace>" not in response.text
    assert "location" not in response.headers
    assert not response.text.lstrip().startswith("{")
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 1
    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    destination = await mongo_db["slack_destinations"].find_one({})
    for sensitive_value in (
        str(workspace["_id"]),
        str(destination["_id"]),
        workspace["slack_team_id"],
        destination["channel_id"],
        "xoxb-private-redirect",
        "https://hooks.slack.com/services/T/B/redirect",
        "installation_id",
        "destination_id",
        "token_hash",
        "ciphertext",
        "client-secret",
        "state-secret",
    ):
        assert sensitive_value not in response.text


@pytest.mark.parametrize(
    ("params", "status_code", "title", "message"),
    [
        (
            {"error": "access_denied"},
            400,
            "Slack Connection Cancelled",
            "Slack authorization was not completed.",
        ),
        (
            {"code": "test-code"},
            400,
            "Slack Connection Failed",
            "This connection link is invalid or has expired.",
        ),
    ],
)
async def test_browser_oauth_errors_return_clean_html(
    client,
    params,
    status_code,
    title,
    message,
):
    response = await client.get(
        "/api/slack/oauth/callback",
        params=params,
        follow_redirects=False,
    )

    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("text/html")
    assert title in response.text
    assert message in response.text
    assert "oauth-card" in response.text
    assert "oauth-icon error" in response.text
    assert "oauth-hint" in response.text
    assert "location" not in response.headers
    assert "test-code" not in response.text


async def test_oauth_exchange_failure_returns_clean_html(
    client,
):
    oauth_service = AsyncMock()
    oauth_service.exchange_code.side_effect = SlackOAuthResponseError(
        "Slack rejected the OAuth exchange"
    )
    state_service = AsyncMock()
    state_service.validate_state.return_value = "client-id"
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    app.dependency_overrides[get_slack_oauth_state_service] = (
        lambda: state_service
    )

    response = await client.get(
        "/api/slack/oauth/callback",
        params={"code": "test-code", "state": "valid-state"},
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("text/html")
    assert "Slack Connection Failed" in response.text
    assert "We could not complete the Slack connection." in response.text
    assert "location" not in response.headers
    assert "test-code" not in response.text
    assert "valid-state" not in response.text
    state_service.validate_state.assert_awaited_once_with("valid-state")


async def test_workspace_conflict_returns_clean_html_without_sensitive_values(
    client,
):
    oauth_service = AsyncMock()
    state_service = AsyncMock()
    installation_service = AsyncMock()
    state_service.validate_state.return_value = "client-id"
    oauth_service.exchange_code.return_value = _installation(
        "T-CONFLICT",
        "Conflict Workspace",
        "C-CONFLICT",
        "#conflict",
        "conflict",
    )
    installation_service.save_installation_and_destination.side_effect = (
        ConflictError("This Slack workspace is already connected")
    )
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    app.dependency_overrides[get_slack_oauth_state_service] = (
        lambda: state_service
    )
    app.dependency_overrides[get_slack_workspace_installation_service] = (
        lambda: installation_service
    )

    response = await client.get(
        "/api/slack/oauth/callback",
        params={"code": "oauth-code", "state": "oauth-state"},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("text/html")
    assert "Slack Connection Failed" in response.text
    assert (
        "This Slack connection link is not valid for the selected workspace."
        in response.text
    )
    assert (
        "Please use the correct Slack Connect URL or contact your StratSync administrator."
        in response.text
    )
    assert "already connected to another StratSync client" not in response.text
    assert "location" not in response.headers
    for sensitive_value in (
        "oauth-code",
        "oauth-state",
        "xoxb-private-conflict",
        "https://hooks.slack.com/services/conflict",
    ):
        assert sensitive_value not in response.text
    state_service.validate_state.assert_awaited_once_with("oauth-state")
    oauth_service.exchange_code.assert_awaited_once_with("oauth-code")


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
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 1

    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    destination = await mongo_db["slack_destinations"].find_one({})
    assert "incoming_webhook" not in workspace
    assert str(workspace["client_id"]) == client_id
    assert destination["client_id"] is not None
    assert str(destination["client_id"]) == client_id
    assert destination["workspace_id"] == "T0C3D4N42MT"
    assert destination["channel_id"] == "C0C32Q6U1JB"
    assert destination["configuration_url"].endswith("/first")
    assert destination["webhook_url"].endswith("/first")
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
    first_installation = await mongo_db[
        "slack_workspace_installations"
    ].find_one({})
    first_installation_id = str(first_installation["_id"])
    second_response = await _connect(
        client, mongo_db, oauth_service, second, client_id
    )

    assert second_response.status_code == 200
    second_installation = await mongo_db[
        "slack_workspace_installations"
    ].find_one({})
    assert str(second_installation["_id"]) == first_installation_id
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
    assert await mongo_db["slack_destinations"].count_documents({}) == 1
    updated = await mongo_db["slack_destinations"].find_one({})
    assert updated["_id"] == original["_id"]

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

    assert response.status_code == 409
    assert await mongo_db["slack_workspace_installations"].count_documents({}) == 1
    assert await mongo_db["slack_destinations"].count_documents({}) == 1
    client_a_channels = (
        await client.get(f"/api/clients/{client_a_id}/slack/channels")
    ).json()["data"]
    client_b_channels = (
        await client.get(f"/api/clients/{client_b_id}/slack/channels")
    ).json()["data"]
    assert len(client_a_channels) == 1
    assert len(client_b_channels) == 0
    assert client_a_channels[0]["client_id"] == client_a_id


async def test_different_client_cannot_connect_another_clients_workspace_channel(
    client,
    mongo_db,
):
    client_a_id = await _create_client(client, "Workspace Owner")
    client_b_id = await _create_client(client, "Workspace Intruder")
    oauth_service = AsyncMock()

    await _connect(
        client,
        mongo_db,
        oauth_service,
        _installation(
            "T-WORKSPACE-OWNER",
            "Owned Workspace",
            "C-ONE",
            "#one",
            "owner",
        ),
        client_a_id,
    )
    response = await _connect(
        client,
        mongo_db,
        oauth_service,
        _installation(
            "T-WORKSPACE-OWNER",
            "Owned Workspace Renamed",
            "C-TWO",
            "#two",
            "intruder",
        ),
        client_b_id,
    )

    assert response.status_code == 409
    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    assert str(workspace["client_id"]) == client_a_id
    assert await mongo_db["slack_destinations"].count_documents({}) == 1


async def test_legacy_null_workspace_is_backfilled_from_single_destination_owner(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Legacy Owner")
    workspace_id = "T-LEGACY-OWNER"
    await mongo_db["slack_workspace_installations"].insert_one(
        {
            "slack_team_id": workspace_id,
            "slack_team_name": "Legacy Workspace",
            "is_active": True,
        }
    )
    await mongo_db["slack_destinations"].insert_one(
        {
            "client_id": ObjectId(client_id),
            "workspace_id": workspace_id,
            "workspace_name": "Legacy Workspace",
            "channel_id": "C-LEGACY-ONE",
            "channel_name": "#one",
            "webhook_url": "https://hooks.slack.com/services/legacy",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    oauth_service = AsyncMock()
    response = await _connect(
        client,
        mongo_db,
        oauth_service,
        _installation(
            workspace_id,
            "Legacy Workspace",
            "C-LEGACY-TWO",
            "#two",
            "legacy-two",
        ),
        client_id,
    )

    assert response.status_code == 200
    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    assert str(workspace["client_id"]) == client_id
    assert await mongo_db["slack_destinations"].count_documents({}) == 2


async def test_legacy_workspace_with_multiple_destination_owners_is_rejected(
    client,
    mongo_db,
):
    client_a_id = await _create_client(client, "Legacy Owner A")
    client_b_id = await _create_client(client, "Legacy Owner B")
    workspace_id = "T-LEGACY-INCONSISTENT"
    await mongo_db["slack_workspace_installations"].insert_one(
        {
            "slack_team_id": workspace_id,
            "slack_team_name": "Inconsistent Workspace",
            "client_id": None,
            "is_active": True,
        }
    )
    for client_id, channel_id in (
        (client_a_id, "C-LEGACY-A"),
        (client_b_id, "C-LEGACY-B"),
    ):
        await mongo_db["slack_destinations"].insert_one(
            {
                "client_id": ObjectId(client_id),
                "workspace_id": workspace_id,
                "workspace_name": "Inconsistent Workspace",
                "channel_id": channel_id,
                "channel_name": channel_id,
                "webhook_url": f"https://hooks.slack.com/services/{channel_id}",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

    oauth_service = AsyncMock()
    response = await _connect(
        client,
        mongo_db,
        oauth_service,
        _installation(
            workspace_id,
            "Inconsistent Workspace",
            "C-LEGACY-NEW",
            "#new",
            "legacy-new",
        ),
        client_a_id,
    )

    assert response.status_code == 409
    workspace = await mongo_db["slack_workspace_installations"].find_one({})
    assert workspace["client_id"] is None
    assert await mongo_db["slack_destinations"].count_documents({}) == 2


async def test_connect_url_is_reusable_and_public_response_is_safe(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Reusable Client")

    first = await client.get(f"/api/clients/{client_id}/slack/connect-url")
    second = await client.get(f"/api/clients/{client_id}/slack/connect-url")

    assert first.status_code == 200
    assert second.status_code == 200
    first_url = first.json()["data"]["connect_url"]
    second_url = second.json()["data"]["connect_url"]
    assert first_url == second_url
    assert client_id not in first_url
    assert "access_token" not in first.text
    assert "webhook" not in first.text.lower()
    assert await mongo_db["slack_connection_tokens"].count_documents({}) == 1
    record = await mongo_db["slack_connection_tokens"].find_one({})
    token = parse_qs(urlparse(first_url).query)["token"][0]
    assert "token" not in record
    assert record["token_hash"] == SlackConnectionTokenService.hash_token(token)
    assert isinstance(record["token_ciphertext"], str)
    assert record["expires_at"] - record["created_at"] == SlackConnectionTokenService.TOKEN_LIFETIME


async def test_connect_url_uses_configured_public_base_url(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        client_api.settings,
        "public_base_url",
        "https://34.100.226.192.nip.io",
    )
    client_id = await _create_client(client, "Configured Public URL Client")

    response = await client.get(f"/api/clients/{client_id}/slack/connect-url")

    assert response.status_code == 200
    connect_url = response.json()["data"]["connect_url"]
    assert connect_url.startswith(
        "https://34.100.226.192.nip.io/api/slack/oauth/start?token="
    )


async def test_expired_connect_url_rotates_lazily_and_old_url_is_rejected(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Rotating Client")
    first = await client.get(f"/api/clients/{client_id}/slack/connect-url")
    first_url = first.json()["data"]["connect_url"]
    first_token = parse_qs(urlparse(first_url).query)["token"][0]
    await mongo_db["slack_connection_tokens"].update_one(
        {},
        {"$set": {"expires_at": datetime.now(timezone.utc)}},
    )

    expired_start = await client.get(
        "/api/slack/oauth/start",
        params={"token": first_token},
        follow_redirects=False,
    )
    assert expired_start.status_code == 410
    assert expired_start.json() == {
        "detail": "This Slack connection link has expired. Please request a new link."
    }

    second = await client.get(f"/api/clients/{client_id}/slack/connect-url")
    second_url = second.json()["data"]["connect_url"]
    second_token = parse_qs(urlparse(second_url).query)["token"][0]
    assert second_token != first_token
    assert await mongo_db["slack_connection_tokens"].count_documents({}) == 2
    assert (
        await mongo_db["slack_connection_tokens"].count_documents(
            {"client_id": ObjectId(client_id), "is_active": True}
        )
        == 1
    )

    old_start = await client.get(
        "/api/slack/oauth/start",
        params={"token": first_token},
        follow_redirects=False,
    )
    assert old_start.status_code == 404


async def test_invalid_token_encryption_configuration_fails_without_persisting(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Invalid Encryption Client")
    settings = Settings.model_construct(
        slack_connection_token_encryption_key="not-a-fernet-key",
    )
    service = SlackConnectionTokenService(
        SlackConnectionTokenRepository(mongo_db),
        ClientRepository(mongo_db),
        settings=settings,
    )

    with pytest.raises(SlackConnectionTokenConfigurationError):
        await service.get_or_create_for_client(client_id)
    assert await mongo_db["slack_connection_tokens"].count_documents({}) == 0


async def test_concurrent_rotation_keeps_one_active_token(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Concurrent Rotation Client")
    first = await client.get(f"/api/clients/{client_id}/slack/connect-url")
    assert first.status_code == 200
    await mongo_db["slack_connection_tokens"].update_one(
        {},
        {"$set": {"expires_at": datetime.now(timezone.utc)}},
    )

    responses = await asyncio.gather(
        *[
            client.get(f"/api/clients/{client_id}/slack/connect-url")
            for _ in range(8)
        ]
    )
    assert all(response.status_code == 200 for response in responses)
    urls = {response.json()["data"]["connect_url"] for response in responses}
    assert len(urls) == 1
    assert await mongo_db["slack_connection_tokens"].count_documents({}) == 2
    assert (
        await mongo_db["slack_connection_tokens"].count_documents(
            {"client_id": ObjectId(client_id), "is_active": True}
        )
        == 1
    )


async def test_client_id_start_parameter_is_not_accepted(client):
    client_id = await _create_client(client, "Secure Start Client")
    response = await client.get(
        "/api/slack/oauth/start",
        params={"client_id": client_id},
        follow_redirects=False,
    )
    assert response.status_code == 422


async def test_oauth_state_is_persistent_single_use_and_replay_is_rejected(
    client,
    mongo_db,
):
    client_id = await _create_client(client, "Single Use Client")
    oauth_service = AsyncMock()
    installation = _installation(
        "T-STATE-CLIENT",
        "State Workspace",
        "C-STATE-CLIENT",
        "#state-alerts",
        "state",
    )
    oauth_service.exchange_code.return_value = installation

    first = await _connect(
        client, mongo_db, oauth_service, installation, client_id
    )
    assert first.status_code == 200
    assert await mongo_db["slack_oauth_states"].count_documents({}) == 1
    state_record = await mongo_db["slack_oauth_states"].find_one({})
    assert state_record["used"] is True
    assert str(state_record["client_id"]) == client_id
    assert state_record["connection_token_id"] is not None

    # The helper creates a fresh state for each attempt; replay the consumed
    # callback state directly to verify the one-time check.
    replay = await client.get(
        "/api/slack/oauth/callback",
        params={"code": "test-code", "state": state_record["state"]},
        follow_redirects=False,
    )
    assert replay.status_code == 400


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
        repository=SlackOAuthStateRepository(mongo_db),
    )
    oauth_service.build_authorization_url = (
        SlackOAuthService(settings).build_authorization_url
    )
    app.dependency_overrides[get_slack_oauth_service] = lambda: oauth_service
    app.dependency_overrides[get_slack_oauth_state_service] = (
        lambda: state_service
    )

    connect_url_response = await client.get(
        f"/api/clients/{client_id}/slack/connect-url",
    )
    token = parse_qs(
        urlparse(connect_url_response.json()["data"]["connect_url"]).query
    )["token"][0]
    start = await client.get(
        "/api/slack/oauth/start",
        params={"token": token},
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    tampered_state = f"{state}tampered"

    response = await client.get(
        "/api/slack/oauth/callback",
        params={"code": "test-code", "state": tampered_state},
        follow_redirects=False,
    )

    assert response.status_code == 400
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
        ("workspace_id", 1),
        ("channel_id", 1),
    ]

    token_indexes = await mongo_db["slack_connection_tokens"].index_information()
    assert token_indexes["uniq_slack_connection_token"]["unique"] is True
    assert token_indexes["uniq_slack_connection_token"]["key"] == [
        ("token_hash", 1)
    ]
    assert token_indexes["uniq_active_slack_connection_token_client"]["unique"] is True
    assert token_indexes["idx_slack_connection_token_expires_at"]["key"] == [
        ("expires_at", 1)
    ]

    state_indexes = await mongo_db["slack_oauth_states"].index_information()
    assert state_indexes["uniq_slack_oauth_state"]["unique"] is True
    assert state_indexes["ttl_slack_oauth_state"]["expireAfterSeconds"] == 0


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
