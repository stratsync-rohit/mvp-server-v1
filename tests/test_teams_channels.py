import pytest
from bson import ObjectId
from unittest.mock import AsyncMock

from app.exceptions import (
    UpstreamConnectionError,
    UpstreamError,
    UpstreamTimeoutError,
)
from app.utils.teams_url_parser import parse_teams_channel_url

pytestmark = pytest.mark.asyncio

VALID_CHANNEL_URL = (
    "https://teams.microsoft.com/l/channel/19%3aabc123%40thread.tacv2/"
    "Risk%20Alerts?groupId=c8931234-aaaa-bbbb-cccc-111122223333"
    "&tenantId=7f301234-dddd-eeee-ffff-444455556666"
)


def _channel_url(team_id: str, channel_id: str, channel_name: str) -> str:
    return (
        f"https://teams.microsoft.com/l/channel/{channel_id}%40thread.tacv2/"
        f"{channel_name}?groupId={team_id}"
        "&tenantId=7f301234-dddd-eeee-ffff-444455556666"
    )


async def _create_client(client) -> str:
    resp = await client.post(
        "/api/clients", json={"name": "ABC Shipping", "code": "ABC-001"}
    )
    return resp.json()["data"]["id"]


def test_teams_url_parser_extracts_fields():
    parsed = parse_teams_channel_url(VALID_CHANNEL_URL)
    assert parsed["channel_id"] == "19:abc123@thread.tacv2"
    assert parsed["channel_name"] == "Risk Alerts"
    assert parsed["team_id"] == "c8931234-aaaa-bbbb-cccc-111122223333"
    assert parsed["tenant_id"] == "7f301234-dddd-eeee-ffff-444455556666"


def test_teams_url_parser_never_raises_on_garbage():
    parsed = parse_teams_channel_url("not a url at all")
    assert parsed == {
        "channel_name": None,
        "channel_id": None,
        "team_id": None,
        "tenant_id": None,
    }
    # Also must not raise on empty / None-like input.
    assert parse_teams_channel_url("") == {
        "channel_name": None,
        "channel_id": None,
        "team_id": None,
        "tenant_id": None,
    }


async def test_create_teams_channel(client):
    client_id = await _create_client(client)

    resp = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-1.westus.logic.azure.com/workflows/abc",
        },
    )
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["team_name"] == "Operations Team"
    assert body["channel_name"] == "Risk Alerts"
    assert body["webhook_configured"] is True
    assert "teams_webhook_url" not in body


async def test_create_teams_channel_invalid_client(client):
    resp = await client.post(
        "/api/clients/000000000000000000000000/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-1.westus.logic.azure.com/workflows/abc",
        },
    )
    assert resp.status_code == 404


async def test_create_teams_channel_rejects_unparseable_url(client):
    client_id = await _create_client(client)

    resp = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": "https://example.com/not-a-teams-link",
            "teams_webhook_url": "https://prod-2.westus.logic.azure.com/workflows/def",
        },
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Invalid Teams channel link"}


async def test_list_teams_channels(client):
    client_id = await _create_client(client)
    await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": _channel_url("TEAM-A", "19%3aone", "Alerts"),
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/a",
        },
    )
    await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Finance",
            "channel_url": _channel_url("TEAM-B", "19%3atwo", "Alerts"),
            "teams_webhook_url": "https://prod-b.logic.azure.com/workflows/b",
        },
    )

    resp = await client.get(f"/api/clients/{client_id}/teams/channels")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


async def test_create_reuses_client_scoped_canonical_team_name(client):
    client_id = await _create_client(client)
    first = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Notification Team",
            "channel_url": _channel_url("TEAM-B", "19%3afirst", "First"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/canonical-first",
        },
    )
    second = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Wrong Manual Label",
            "channel_url": _channel_url("TEAM-B", "19%3asecond", "Second"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/canonical-second",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["team_name"] == "Notification Team"
    assert second.json()["data"]["team_name"] == "Notification Team"
    assert second.json()["data"]["team_id"] == "TEAM-B"


async def test_create_team_name_is_scoped_per_client(client):
    first_client = await _create_client(client)
    second_client = await _create_client(client)
    first = await client.post(
        f"/api/clients/{first_client}/teams/channels",
        json={
            "team_name": "Client One Label",
            "channel_url": _channel_url("SHARED-TEAM", "19%3afirst", "First"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/client-one",
        },
    )
    second = await client.post(
        f"/api/clients/{second_client}/teams/channels",
        json={
            "team_name": "Client Two Label",
            "channel_url": _channel_url("SHARED-TEAM", "19%3asecond", "Second"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/client-two",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["team_name"] == "Client One Label"
    assert second.json()["data"]["team_name"] == "Client Two Label"


async def test_create_rejects_duplicate_channel_identity(client):
    client_id = await _create_client(client)
    link = _channel_url("TEAM-DUP", "19%3aduplicate", "Alerts")
    first = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": link,
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/duplicate-one",
        },
    )
    second = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Another Label",
            "channel_url": link,
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/duplicate-two",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {
        "detail": "This Teams channel is already configured"
    }


async def test_edit_team_name_updates_every_channel_in_team(client):
    client_id = await _create_client(client)
    created_ids = []
    for suffix in ("first", "second"):
        created = await client.post(
            f"/api/clients/{client_id}/teams/channels",
            json={
                "team_name": "Original Team",
                "channel_url": _channel_url(
                    "TEAM-RENAME", f"19%3a{suffix}", suffix.title()
                ),
                "teams_webhook_url": f"https://prod.logic.azure.com/workflows/rename-{suffix}",
            },
        )
        created_ids.append(created.json()["data"]["id"])

    response = await client.put(
        f"/api/teams/channels/{created_ids[0]}",
        json={"team_name": "Renamed Team"},
    )
    listed = await client.get(f"/api/clients/{client_id}/teams/channels")

    assert response.status_code == 200
    assert {item["team_name"] for item in listed.json()["data"]} == {
        "Renamed Team"
    }


async def test_edit_move_to_existing_team_reuses_canonical_name(client):
    client_id = await _create_client(client)
    source = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Source Team",
            "channel_url": _channel_url("TEAM-SOURCE", "19%3asource", "Source"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/move-source",
        },
    )
    await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Canonical Target",
            "channel_url": _channel_url("TEAM-TARGET", "19%3atarget", "Target"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/move-target",
        },
    )

    moved = await client.put(
        f"/api/teams/channels/{source.json()['data']['id']}",
        json={
            "team_name": "Ignored Manual Label",
            "channel_url": _channel_url("TEAM-TARGET", "19%3amoved", "Moved"),
        },
    )

    assert moved.status_code == 200
    assert moved.json()["data"]["team_id"] == "TEAM-TARGET"
    assert moved.json()["data"]["channel_name"] == "Moved"
    assert moved.json()["data"]["team_name"] == "Canonical Target"


async def test_get_destinations_includes_identity_without_webhook(client):
    client_id = await _create_client(client)
    await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Identity Team",
            "channel_url": _channel_url("TEAM-ID", "19%3achannel-id", "Alerts"),
            "teams_webhook_url": "https://prod.logic.azure.com/workflows/identity-secret",
        },
    )

    response = await client.get(f"/api/clients/{client_id}/teams/channels")
    destination = response.json()["data"][0]

    assert destination["team_id"] == "TEAM-ID"
    assert destination["channel_id"] == "19:channel-id@thread.tacv2"
    assert "teams_webhook_url" not in destination
    assert "identity-secret" not in response.text


async def test_dashboard_teams_channels_omit_internal_ids(client):
    client_id = await _create_client(client)
    await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-safe.logic.azure.com/workflows/secret",
        },
    )

    resp = await client.get(
        f"/api/clients/{client_id}/teams/channels",
        params={"dashboard": "true"},
    )

    assert resp.status_code == 200
    destination = resp.json()["data"][0]
    assert set(destination) == {
        "id",
        "client_id",
        "team_name",
        "team_id",
        "channel_name",
        "channel_id",
        "webhook_configured",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert "secret" not in resp.text
    assert "tenant_id" not in destination
    assert destination["team_id"] == "c8931234-aaaa-bbbb-cccc-111122223333"
    assert destination["channel_id"] == "19:abc123@thread.tacv2"


async def test_get_teams_destination_success(client):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/a",
        },
    )
    destination_id = created.json()["data"]["id"]

    resp = await client.get(f"/api/teams/channels/{destination_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["id"] == destination_id
    assert body["data"]["client_id"] == client_id
    assert body["data"]["team_name"] == "Operations Team"
    assert body["data"]["channel_name"] == "Risk Alerts"


async def test_get_teams_destination_invalid_id(client):
    resp = await client.get("/api/teams/channels/not-an-object-id")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Teams destination not found"


async def test_get_teams_destination_not_found(client):
    resp = await client.get(f"/api/teams/channels/{ObjectId()}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Teams destination not found"


async def test_webhook_never_exposed_in_get(client):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": _channel_url("TEAM-SECRET", "19%3asecret", "Secret"),
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/SECRET-TOKEN",
        },
    )
    integration_id = created.json()["data"]["id"]

    resp = await client.get(f"/api/teams/channels/{integration_id}")
    body_text = resp.text
    assert "SECRET-TOKEN" not in body_text
    assert "teams_webhook_url" not in resp.json()["data"]


async def test_update_destination_preserves_identity_and_blank_webhook(
    client, mongo_db
):
    client_id = await _create_client(client)
    webhook = "https://prod-a.logic.azure.com/workflows/original-secret"
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": webhook,
        },
    )
    original = created.json()["data"]
    destination_id = original["id"]
    stored_before = await mongo_db["teams_channels"].find_one(
        {"_id": ObjectId(destination_id)}
    )

    disabled = await client.put(
        f"/api/teams/channels/{destination_id}",
        json={
            "team_name": "  Operations Team  ",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "",
            "is_active": False,
        },
    )

    assert disabled.status_code == 200
    body = disabled.json()
    assert body["message"] == "Teams destination updated successfully"
    assert body["data"]["team_name"] == "Operations Team"
    assert body["data"]["is_active"] is False
    assert body["data"]["client_id"] == client_id
    assert body["data"]["updated_at"] != original["updated_at"]
    assert "teams_webhook_url" not in body["data"]
    assert "original-secret" not in disabled.text

    stored = await mongo_db["teams_channels"].find_one(
        {"_id": ObjectId(destination_id)}
    )
    assert stored["teams_webhook_url"] == webhook
    assert str(stored["client_id"]) == client_id
    assert stored["created_at"] == stored_before["created_at"]
    assert stored["updated_at"] != stored_before["updated_at"]

    enabled = await client.put(
        f"/api/teams/channels/{destination_id}",
        json={"is_active": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["is_active"] is True


async def test_update_destination_reparses_link_and_replaces_webhook(
    client, mongo_db
):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/old-secret",
        },
    )
    destination_id = created.json()["data"]["id"]
    new_link = (
        "https://teams.microsoft.com/l/channel/19%3anew-channel%40thread.tacv2/"
        "Executive%20Alerts?groupId=11111111-2222-3333-4444-555555555555"
        "&tenantId=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )
    new_webhook = "https://prod-b.logic.azure.com/workflows/new-secret"

    response = await client.put(
        f"/api/teams/channels/{destination_id}",
        json={
            "channel_url": new_link,
            "teams_webhook_url": new_webhook,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["channel_name"] == "Executive Alerts"
    assert data["channel_id"] == "19:new-channel@thread.tacv2"
    assert data["team_id"] == "11111111-2222-3333-4444-555555555555"
    assert data["tenant_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert data["webhook_configured"] is True
    assert "teams_webhook_url" not in data
    assert "new-secret" not in response.text
    stored = await mongo_db["teams_channels"].find_one(
        {"_id": ObjectId(destination_id)}
    )
    assert stored["teams_webhook_url"] == new_webhook


async def test_update_destination_validation_errors(client):
    invalid = await client.put(
        "/api/teams/channels/not-an-object-id",
        json={"team_name": "Operations"},
    )
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Invalid Teams destination ID"}

    missing = await client.put(
        f"/api/teams/channels/{ObjectId()}",
        json={"team_name": "Operations"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Teams destination not found"}

    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/valid",
        },
    )
    destination_id = created.json()["data"]["id"]
    invalid_link = await client.put(
        f"/api/teams/channels/{destination_id}",
        json={"channel_url": "https://example.com/not-a-teams-link"},
    )
    assert invalid_link.status_code == 400
    assert invalid_link.json() == {"detail": "Invalid Teams channel link"}


async def test_update_destination_rejects_duplicate_replacement_webhook(client):
    client_id = await _create_client(client)
    shared = "https://prod-a.logic.azure.com/workflows/shared-update-secret"
    first = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": _channel_url("TEAM-ONE", "19%3aone", "One"),
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/one",
        },
    )
    await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Finance",
            "channel_url": _channel_url("TEAM-TWO", "19%3atwo", "Two"),
            "teams_webhook_url": shared,
        },
    )

    response = await client.put(
        f"/api/teams/channels/{first.json()['data']['id']}",
        json={"teams_webhook_url": shared},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This Teams webhook is already configured"
    }
    assert "shared-update-secret" not in response.text


async def test_teams_destination_test_success(client, mock_n8n_service):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/secret",
        },
    )
    destination_id = created.json()["data"]["id"]

    resp = await client.post(f"/api/teams/channels/{destination_id}/test")

    assert resp.status_code == 200
    assert resp.json() == {
        "success": True,
        "message": "Test notification sent successfully",
        "data": {
            "destination_id": destination_id,
            "team_name": "Operations Team",
            "channel_name": "Risk Alerts",
        },
    }
    assert "secret" not in resp.text
    assert "stratsync-n8n" not in resp.text
    mock_n8n_service.trigger_notification.assert_awaited_once()
    sent_payload = mock_n8n_service.trigger_notification.call_args.args[0]
    assert set(sent_payload) == {"teams_webhook_url", "risk"}
    assert sent_payload["teams_webhook_url"].endswith("/secret")
    assert sent_payload["risk"]["risk_id"] == "TEST-INTEGRATION"
    assert sent_payload["risk"]["subtitle"] == "Operations Team · Risk Alerts"
    assert sent_payload["risk"]["details"]["facts"] == [
        {"label": "Team", "value": "Operations Team"},
        {"label": "Channel", "value": "Risk Alerts"},
    ]
    assert "_id" not in sent_payload["risk"]


async def test_teams_destination_test_invalid_destination(client):
    resp = await client.post("/api/teams/channels/invalid-id/test")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Teams destination not found"}


async def test_teams_destination_test_destination_not_found(client):
    resp = await client.post(f"/api/teams/channels/{ObjectId()}/test")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Teams destination not found"}


async def test_teams_destination_test_inactive(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/inactive",
        },
    )
    destination_id = created.json()["data"]["id"]
    await mongo_db["teams_channels"].update_one(
        {"_id": ObjectId(destination_id)},
        {"$set": {"is_active": False}},
    )

    resp = await client.post(f"/api/teams/channels/{destination_id}/test")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Teams destination is inactive"
    mock_n8n_service.trigger_notification.assert_not_awaited()


async def test_teams_destination_test_client_inactive(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/inactive-client",
        },
    )
    destination_id = created.json()["data"]["id"]
    await mongo_db["clients"].update_one(
        {"_id": ObjectId(client_id)},
        {"$set": {"is_active": False}},
    )

    resp = await client.post(f"/api/teams/channels/{destination_id}/test")

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Client is inactive"}
    mock_n8n_service.trigger_notification.assert_not_awaited()


async def test_teams_destination_test_webhook_missing(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/missing",
        },
    )
    destination_id = created.json()["data"]["id"]
    await mongo_db["teams_channels"].update_one(
        {"_id": ObjectId(destination_id)},
        {"$unset": {"teams_webhook_url": ""}},
    )

    resp = await client.post(f"/api/teams/channels/{destination_id}/test")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Teams webhook is not configured"
    mock_n8n_service.trigger_notification.assert_not_awaited()


@pytest.mark.parametrize(
    "upstream_error",
    [
        UpstreamTimeoutError("private timeout detail"),
        UpstreamConnectionError("private connection detail"),
        UpstreamError(
            "private delivery detail",
            error_code="n8n_delivery_failed",
            http_status=500,
        ),
    ],
)
async def test_teams_destination_test_n8n_failure(
    client, mock_n8n_service, upstream_error
):
    client_id = await _create_client(client)
    created = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": "https://prod-a.logic.azure.com/workflows/failure",
        },
    )
    destination_id = created.json()["data"]["id"]
    mock_n8n_service.trigger_notification = AsyncMock(
        side_effect=upstream_error
    )

    resp = await client.post(f"/api/teams/channels/{destination_id}/test")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Unable to send test notification"
    assert "private" not in resp.text
    assert "stratsync-n8n" not in resp.text


async def test_duplicate_webhook_rejected(client):
    client_id = await _create_client(client)
    webhook = "https://prod-a.logic.azure.com/workflows/shared-secret"

    first = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations",
            "channel_url": _channel_url("TEAM-A", "19%3aone", "One"),
            "teams_webhook_url": webhook,
        },
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Finance",
            "channel_url": _channel_url("TEAM-B", "19%3atwo", "Two"),
            "teams_webhook_url": webhook,
        },
    )
    assert second.status_code == 409
    assert "shared-secret" not in second.text
