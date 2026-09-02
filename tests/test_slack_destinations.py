from datetime import datetime, timedelta, timezone
import pytest
from bson import ObjectId

from app.dependencies import get_slack_n8n_service
from app.exceptions import UpstreamError, UpstreamTimeoutError
from app.main import app
from app.services.slack_destination_service import SLACK_TEST_MESSAGE
from app.utils.slack_url_parser import (
    is_valid_slack_webhook_url,
    parse_slack_channel_link,
)

pytestmark = pytest.mark.asyncio

CHANNEL_LINK = "https://stratsyncworkspace.slack.com/archives/C0BMC4NDPKJ"
WEBHOOK_URL = "https://hooks.slack.com/services/T000/B000/secret-token"


async def _create_client(client, suffix="001") -> str:
    response = await client.post(
        "/api/clients",
        json={"name": f"Slack Client {suffix}", "code": f"SLACK-{suffix}"},
    )
    return response.json()["data"]["id"]


async def _create_destination(client, client_id, **overrides):
    payload = {
        "channel_link": CHANNEL_LINK,
        "channel_name": "risk-alerts",
        "webhook_url": WEBHOOK_URL,
    }
    payload.update(overrides)
    return await client.post(
        f"/api/clients/{client_id}/slack/channels", json=payload
    )


def test_slack_channel_link_parser():
    assert parse_slack_channel_link(f"  {CHANNEL_LINK}  ") == {
        "workspace_domain": "stratsyncworkspace",
        "channel_id": "C0BMC4NDPKJ",
    }
    for invalid in (
        "http://workspace.slack.com/archives/C123",
        "https://slack.com/archives/C123",
        "https://workspace.example.com/archives/C123",
        "https://workspace.slack.com/messages/C123",
        "https://workspace.slack.com/archives/",
    ):
        assert parse_slack_channel_link(invalid) == {
            "workspace_domain": None,
            "channel_id": None,
        }


def test_slack_webhook_url_validator():
    assert is_valid_slack_webhook_url(WEBHOOK_URL)
    assert not is_valid_slack_webhook_url(
        "http://hooks.slack.com/services/T000/B000/secret"
    )
    assert not is_valid_slack_webhook_url(
        "https://evil.example/services/T000/B000/secret"
    )
    assert not is_valid_slack_webhook_url("https://hooks.slack.com/not-services")


async def test_create_get_and_list_slack_destination(client, mongo_db):
    client_id = await _create_client(client)
    response = await _create_destination(
        client,
        client_id,
        channel_link=f"  {CHANNEL_LINK}  ",
        channel_name="  Risk Alerts  ",
        webhook_url=f"  {WEBHOOK_URL}  ",
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["client_id"] == client_id
    assert data["workspace_domain"] == "stratsyncworkspace"
    assert data["channel_id"] == "C0BMC4NDPKJ"
    assert data["channel_name"] == "Risk Alerts"
    assert data["channel_link"] == CHANNEL_LINK
    assert data["webhook_configured"] is True
    assert "webhook_url" not in data
    assert "secret-token" not in response.text

    stored = await mongo_db["slack_destinations"].find_one(
        {"_id": ObjectId(data["id"])}
    )
    assert stored["webhook_url"] == WEBHOOK_URL

    fetched = await client.get(f"/api/slack/channels/{data['id']}")
    listed = await client.get(f"/api/clients/{client_id}/slack/channels")
    assert fetched.status_code == 200
    fetched_data = fetched.json()["data"]
    assert {
        key: value
        for key, value in fetched_data.items()
        if key not in {"created_at", "updated_at"}
    } == {
        key: value
        for key, value in data.items()
        if key not in {"created_at", "updated_at"}
    }
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == data["id"]
    assert "secret-token" not in fetched.text + listed.text


@pytest.mark.parametrize(
    ("link", "webhook", "detail"),
    [
        (
            "https://example.com/archives/C123",
            WEBHOOK_URL,
            "Invalid Slack channel link",
        ),
        (
            CHANNEL_LINK,
            "https://evil.example/services/T/B/private-secret",
            "Invalid Slack webhook URL",
        ),
    ],
)
async def test_create_rejects_invalid_urls_without_leaking_secret(
    client, link, webhook, detail
):
    client_id = await _create_client(client)
    response = await _create_destination(
        client, client_id, channel_link=link, webhook_url=webhook
    )
    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    assert "private-secret" not in response.text


async def test_create_rejects_missing_or_inactive_client(client, mongo_db):
    missing = await _create_destination(client, str(ObjectId()))
    invalid = await _create_destination(client, "invalid-id")
    assert missing.status_code == 404
    assert invalid.status_code == 404

    client_id = await _create_client(client)
    await mongo_db["clients"].update_one(
        {"_id": ObjectId(client_id)}, {"$set": {"is_active": False}}
    )
    inactive = await _create_destination(client, client_id)
    assert inactive.status_code == 400
    assert inactive.json() == {"detail": "Client is inactive"}


async def test_duplicate_active_identity_is_conflict(client):
    client_id = await _create_client(client)
    assert (await _create_destination(client, client_id)).status_code == 201
    duplicate = await _create_destination(
        client,
        client_id,
        channel_name="renamed-channel",
        webhook_url="https://hooks.slack.com/services/T111/B111/another-secret",
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "This Slack channel is already configured"
    }
    assert "another-secret" not in duplicate.text


async def test_list_is_newest_first_and_includes_inactive(client, mongo_db):
    client_id = await _create_client(client)
    first = await _create_destination(client, client_id)
    second = await _create_destination(
        client,
        client_id,
        channel_link="https://other-workspace.slack.com/archives/C222",
        webhook_url="https://hooks.slack.com/services/T222/B222/secret",
    )
    now = datetime.now(timezone.utc)
    await mongo_db["slack_destinations"].update_one(
        {"_id": ObjectId(first.json()["data"]["id"])},
        {"$set": {"created_at": now - timedelta(seconds=1)}},
    )
    await mongo_db["slack_destinations"].update_one(
        {"_id": ObjectId(second.json()["data"]["id"])},
        {"$set": {"created_at": now}},
    )
    await client.delete(f"/api/slack/channels/{first.json()['data']['id']}")

    response = await client.get(f"/api/clients/{client_id}/slack/channels")
    data = response.json()["data"]
    assert [item["id"] for item in data] == [
        second.json()["data"]["id"],
        first.json()["data"]["id"],
    ]
    assert data[1]["is_active"] is False


async def test_update_reparses_link_and_preserves_blank_webhook(client, mongo_db):
    client_id = await _create_client(client)
    created = await _create_destination(client, client_id)
    destination_id = created.json()["data"]["id"]

    response = await client.put(
        f"/api/slack/channels/{destination_id}",
        json={
            "channel_link": "https://newspace.slack.com/archives/C999",
            "channel_name": "  executive-alerts  ",
            "webhook_url": "   ",
            "is_active": False,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["workspace_domain"] == "newspace"
    assert data["channel_id"] == "C999"
    assert data["channel_name"] == "executive-alerts"
    assert data["is_active"] is False
    assert "secret-token" not in response.text

    stored = await mongo_db["slack_destinations"].find_one(
        {"_id": ObjectId(destination_id)}
    )
    assert stored["webhook_url"] == WEBHOOK_URL


async def test_update_replaces_valid_webhook(client, mongo_db):
    client_id = await _create_client(client)
    created = await _create_destination(client, client_id)
    destination_id = created.json()["data"]["id"]
    replacement = "https://hooks.slack.com/services/T999/B999/new-secret"
    response = await client.put(
        f"/api/slack/channels/{destination_id}",
        json={"webhook_url": replacement},
    )
    assert response.status_code == 200
    assert "new-secret" not in response.text
    stored = await mongo_db["slack_destinations"].find_one(
        {"_id": ObjectId(destination_id)}
    )
    assert stored["webhook_url"] == replacement


async def test_soft_delete_allows_readding_but_blocks_duplicate_reactivation(client):
    client_id = await _create_client(client)
    first = await _create_destination(client, client_id)
    destination_id = first.json()["data"]["id"]

    deleted = await client.delete(f"/api/slack/channels/{destination_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["is_active"] is False

    replacement = await _create_destination(
        client,
        client_id,
        webhook_url="https://hooks.slack.com/services/TNEW/BNEW/new-secret",
    )
    assert replacement.status_code == 201

    reactivated = await client.put(
        f"/api/slack/channels/{destination_id}", json={"is_active": True}
    )
    assert reactivated.status_code == 409


async def test_invalid_and_missing_destination_responses(client):
    for method in (client.get, client.delete):
        response = await method("/api/slack/channels/invalid-id")
        assert response.status_code == 404
    update = await client.put(
        "/api/slack/channels/invalid-id", json={"channel_name": "alerts"}
    )
    assert update.status_code == 400
    missing = await client.get(f"/api/slack/channels/{ObjectId()}")
    assert missing.status_code == 404


async def test_slack_destination_test_uses_n8n_with_expected_payload(
    client, mock_slack_n8n_service, caplog
):
    client_id = await _create_client(client)
    created = await _create_destination(client, client_id)
    destination_id = created.json()["data"]["id"]

    response = await client.post(f"/api/slack/channels/{destination_id}/test")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "sent",
        "message": "Slack test notification sent successfully.",
    }
    mock_slack_n8n_service.trigger_notification.assert_awaited_once_with(
        {
            "platform": "slack",
            "mode": "test",
            "destination_id": destination_id,
            "client_id": client_id,
            "workspace_domain": "stratsyncworkspace",
            "channel_id": "C0BMC4NDPKJ",
            "channel_name": "risk-alerts",
            "slack_webhook_url": WEBHOOK_URL,
            "message": SLACK_TEST_MESSAGE,
        }
    )
    assert "slack_webhook_url" not in response.text
    assert "secret-token" not in response.text
    assert "secret-token" not in caplog.text


async def test_slack_destination_test_rejects_invalid_inactive_and_missing_webhook(
    client, mongo_db, mock_slack_n8n_service
):
    invalid = await client.post("/api/slack/channels/invalid-id/test")
    assert invalid.status_code == 404

    client_id = await _create_client(client)
    created = await _create_destination(client, client_id)
    destination_id = created.json()["data"]["id"]
    await mongo_db["slack_destinations"].update_one(
        {"_id": ObjectId(destination_id)}, {"$set": {"is_active": False}}
    )
    inactive = await client.post(f"/api/slack/channels/{destination_id}/test")
    assert inactive.status_code == 400
    assert inactive.json() == {"detail": "Slack destination is inactive"}

    await mongo_db["slack_destinations"].update_one(
        {"_id": ObjectId(destination_id)},
        {"$set": {"is_active": True}, "$unset": {"webhook_url": ""}},
    )
    missing_webhook = await client.post(
        f"/api/slack/channels/{destination_id}/test"
    )
    assert missing_webhook.status_code == 400
    assert missing_webhook.json() == {
        "detail": "Slack webhook is not configured"
    }
    mock_slack_n8n_service.trigger_notification.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        UpstreamTimeoutError("private n8n timeout"),
        UpstreamError("private n8n non-2xx"),
    ],
)
async def test_slack_destination_test_n8n_failure_is_sanitized(
    client, mock_slack_n8n_service, caplog, error
):
    client_id = await _create_client(client)
    created = await _create_destination(client, client_id)
    destination_id = created.json()["data"]["id"]
    mock_slack_n8n_service.trigger_notification.side_effect = error

    response = await client.post(f"/api/slack/channels/{destination_id}/test")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Unable to send Slack test notification"
    }
    assert "private n8n" not in response.text
    assert "secret-token" not in response.text
    assert "secret-token" not in caplog.text


async def test_slack_destination_test_missing_n8n_config_is_sanitized(
    client, caplog
):
    from app.config import Settings
    from app.services.n8n_service import N8nService

    settings = Settings(_env_file=None, SLACK_N8N_WEBHOOK_URL=None)
    app.dependency_overrides[get_slack_n8n_service] = lambda: N8nService(
        settings, webhook_url=None
    )
    client_id = await _create_client(client)
    created = await _create_destination(client, client_id)
    destination_id = created.json()["data"]["id"]

    response = await client.post(f"/api/slack/channels/{destination_id}/test")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Unable to send Slack test notification"
    }
    assert "secret-token" not in response.text
    assert "secret-token" not in caplog.text


async def test_slack_indexes_exist(mongo_db):
    indexes = await mongo_db["slack_destinations"].index_information()
    assert "idx_slack_destinations_client_id" in indexes
    identity = indexes["uniq_active_slack_destination_identity"]
    assert identity["unique"] is True
    assert identity["partialFilterExpression"] == {"is_active": True}
