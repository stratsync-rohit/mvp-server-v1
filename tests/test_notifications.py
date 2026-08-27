from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from bson import ObjectId

from app.exceptions import (
    UpstreamConnectionError,
    UpstreamConfigurationError,
    UpstreamError,
    UpstreamTimeoutError
)


pytestmark = pytest.mark.asyncio

VALID_CHANNEL_URL = (
    "https://teams.microsoft.com/l/channel/19%3anotify%40thread.tacv2/"
    "Risk%20Alerts?groupId=c8931234-aaaa-bbbb-cccc-111122223333"
    "&tenantId=7f301234-dddd-eeee-ffff-444455556666"
)
WEBHOOK = "https://prod-a.logic.azure.com/workflows/private-secret"


async def _create_client(client, code="ABC-001") -> str:
    response = await client.post(
        "/api/clients",
        json={"name": "ABC Shipping", "code": code}
    )
    return response.json()["data"]["id"]


async def _create_channel(client, client_id: str, webhook=WEBHOOK) -> str:
    response = await client.post(
        f"/api/clients/{client_id}/teams/channels",
        json={
            "team_name": "Operations Team",
            "channel_url": VALID_CHANNEL_URL,
            "teams_webhook_url": webhook,
        },
    )
    return response.json()["data"]["id"]


async def _trigger(client, destination_id: str, risk_id="RSK-21132-0472"):
    return await client.post(
        "/api/notifications/trigger",
        json={"risk_id": risk_id, "destination_id": destination_id}
    )


async def test_notification_trigger_success_and_history_created(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    nested_id = ObjectId()
    detected_at = datetime.now(timezone.utc)
    await mongo_db["risks"].update_one(
        {"risk_id": "RSK-21132-0472"},
        {
            "$set": {
                "industry_slug": "distribution-trading",
                "metrics": [{"label": "Exposure", "value": "$84,000"}],
                "supplier_comparison": [{"supplier": "Supplier A1"}],
                "nested_id": nested_id,
                "detected_at": detected_at,
                "severity": "high",
            }
        },
    )

    response = await _trigger(client, destination_id)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Notification sent successfully"
    assert body["data"]["risk_id"] == "RSK-21132-0472"
    assert body["data"]["destination_id"] == destination_id
    assert body["data"]["status"] == "sent"
    assert "teams_webhook_url" not in response.text
    assert "private-secret" not in response.text

    mock_n8n_service.trigger_notification.assert_awaited_once()
    n8n_payload = mock_n8n_service.trigger_notification.call_args.args[0]
    assert set(n8n_payload) == {"teams_webhook_url", "risk"}
    assert n8n_payload["teams_webhook_url"] == WEBHOOK
    assert n8n_payload["risk"]["risk_id"] == "RSK-21132-0472"
    assert n8n_payload["risk"]["metrics"][0]["value"] == "$84,000"
    assert n8n_payload["risk"]["supplier_comparison"] == [
        {"supplier": "Supplier A1"}
    ]
    assert n8n_payload["risk"]["nested_id"] == str(nested_id)
    assert isinstance(n8n_payload["risk"]["detected_at"], str)
    assert n8n_payload["risk"]["detected_at"].startswith(
        detected_at.strftime("%Y-%m-%dT%H:%M:%S")
    )
    assert "_id" not in n8n_payload["risk"]
    assert "id" not in n8n_payload["risk"]

    history = await mongo_db["notifications"].find_one({
        "_id": ObjectId(body["data"]["notification_id"])
    })
    assert history["status"] == "sent"
    assert history["destination_id"] == ObjectId(destination_id)
    assert history["client_id"] == ObjectId(client_id)
    assert "teams_webhook_url" not in history
    assert "sent_at" in history


async def test_notification_request_accepts_only_ids(client):
    response = await client.post(
        "/api/notifications/trigger",
        json={
            "risk_id": "RSK-21132-0472",
            "destination_id": str(ObjectId()),
            "teams_webhook_url": WEBHOOK,
        },
    )
    assert response.status_code == 422


async def test_notification_request_rejects_blank_ids(client):
    response = await client.post(
        "/api/notifications/trigger",
        json={"risk_id": "   ", "destination_id": "   "},
    )
    assert response.status_code == 422


async def test_notification_risk_not_found(client, mock_n8n_service):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    response = await _trigger(client, destination_id, "UNKNOWN-RISK")
    assert response.status_code == 404
    assert response.json() == {"detail": "Risk not found"}
    mock_n8n_service.trigger_notification.assert_not_awaited()


async def test_notification_destination_not_found(client, mock_n8n_service):
    response = await _trigger(client, str(ObjectId()))
    assert response.status_code == 404
    assert response.json() == {"detail": "Teams destination not found"}
    mock_n8n_service.trigger_notification.assert_not_awaited()


async def test_notification_destination_inactive(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    await mongo_db["teams_channels"].update_one(
        {"_id": ObjectId(destination_id)},
        {"$set": {"is_active": False}},
    )
    response = await _trigger(client, destination_id)
    assert response.status_code == 400
    assert response.json() == {"detail": "Teams destination is inactive"}
    mock_n8n_service.trigger_notification.assert_not_awaited()


async def test_notification_client_inactive(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    await mongo_db["clients"].update_one(
        {"_id": ObjectId(client_id)},
        {"$set": {"is_active": False}},
    )

    response = await _trigger(client, destination_id)

    assert response.status_code == 400
    assert response.json() == {"detail": "Client is inactive"}
    mock_n8n_service.trigger_notification.assert_not_awaited()
    assert await mongo_db["notifications"].count_documents({}) == 0


async def test_notification_webhook_missing(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    await mongo_db["teams_channels"].update_one(
        {"_id": ObjectId(destination_id)},
        {"$unset": {"teams_webhook_url": ""}},
    )
    response = await _trigger(client, destination_id)
    assert response.status_code == 400
    assert response.json() == {"detail": "Teams webhook is not configured"}
    mock_n8n_service.trigger_notification.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "failure_reason"),
    [
        (UpstreamTimeoutError("private timeout detail"), "n8n_timeout"),
        (
            UpstreamConnectionError("private connection detail"),
            "n8n_connection_failed",
        ),
        (UpstreamError("private delivery detail"), "n8n_delivery_failed"),
    ],
)
async def test_notification_n8n_failure_creates_safe_history(
    client, mongo_db, mock_n8n_service, error, failure_reason
):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    mock_n8n_service.trigger_notification = AsyncMock(side_effect=error)
    response = await _trigger(client, destination_id)
    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to send notification"}
    assert "private" not in response.text
    history = await mongo_db["notifications"].find_one({
        "destination_id": ObjectId(destination_id)
    })
    assert history["status"] == "failed"
    assert history["failure_reason"] == failure_reason
    assert "teams_webhook_url" not in history


async def test_notification_duplicate_rapid_trigger_is_blocked(
    client, mongo_db, mock_n8n_service
):
    client_id = await _create_client(client)
    destination_id = await _create_channel(client, client_id)
    first = await _trigger(client, destination_id)
    second = await _trigger(client, destination_id)
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == {
        "detail": "Notification was already triggered recently"
    }
    assert mock_n8n_service.trigger_notification.await_count == 1
    assert await mongo_db["notifications"].count_documents({}) == 1


async def test_get_notifications_newest_first_and_never_exposes_webhook(
    client, mongo_db
):
    now = datetime.now(timezone.utc)
    client_id = ObjectId()
    destination_id = ObjectId()
    await mongo_db["notifications"].insert_many([
        {
            "risk_id": "OLDER-RISK",
            "risk_title": "Older risk",
            "destination_id": destination_id,
            "client_id": client_id,
            "team_name": "Operations Team",
            "channel_name": "Risk Alerts",
            "severity": "low",
            "status": "sent",
            "sent_at": now - timedelta(minutes=2),
            "created_at": now - timedelta(minutes=2),
        },
        {
            "risk_id": "NEWER-RISK",
            "risk_title": "Newer risk",
            "destination_id": destination_id,
            "client_id": client_id,
            "team_name": "Operations Team",
            "channel_name": "Risk Alerts",
            "severity": "high",
            "status": "failed",
            "failure_reason": "n8n_delivery_failed",
            "created_at": now,
        },
    ])
    response = await client.get("/api/notifications")
    assert response.status_code == 200
    assert [item["risk_id"] for item in response.json()["data"]] == [
        "NEWER-RISK",
        "OLDER-RISK",
    ]
    assert "teams_webhook_url" not in response.text
    assert all("_id" not in item for item in response.json()["data"])
    assert all("id" in item for item in response.json()["data"])


async def test_get_notifications_filters(client, mongo_db):
    now = datetime.now(timezone.utc)
    client_a = ObjectId()
    client_b = ObjectId()
    destination_a = ObjectId()
    destination_b = ObjectId()
    base = {
        "risk_title": "Risk",
        "team_name": "Team",
        "channel_name": "Channel",
        "severity": "high",
        "created_at": now,
    }
    await mongo_db["notifications"].insert_many([
        {
            **base,
            "risk_id": "FILTER-ME",
            "destination_id": destination_a,
            "client_id": client_a,
            "status": "sent",
            "sent_at": now,
        },
        {
            **base,
            "risk_id": "OTHER-RISK",
            "destination_id": destination_b,
            "client_id": client_b,
            "status": "failed",
            "failure_reason": "n8n_timeout",
        },
    ])
    filter_sets = [
        ({"client_id": str(client_a)}, "FILTER-ME"),
        ({"risk_id": "FILTER-ME"}, "FILTER-ME"),
        ({"status": "failed"}, "OTHER-RISK"),
        ({"destination_id": str(destination_b)}, "OTHER-RISK"),
    ]
    for params, expected_risk_id in filter_sets:
        response = await client.get("/api/notifications", params=params)
        assert response.status_code == 200
        assert [item["risk_id"] for item in response.json()["data"]] == [
            expected_risk_id
        ]


async def test_n8n_service_translates_http_errors_without_leaking_urls():
    from app.config import Settings
    from app.services.n8n_service import N8nService
    import app.services.n8n_service as n8n_module

    settings = Settings(
        N8N_NOTIFICATION_WEBHOOK_URL="http://private-n8n.invalid/webhook/x"
    )
    service = N8nService(settings)
    cases = [
        (httpx.TimeoutException("secret timeout"), UpstreamTimeoutError),
        (httpx.ConnectError("secret connection"), UpstreamConnectionError),
        (
            httpx.RequestError(
                "secret request",
                request=httpx.Request("POST", "http://private.invalid"),
            ),
            UpstreamConnectionError,
        ),
        (
            httpx.HTTPStatusError(
                "secret response",
                request=httpx.Request("POST", "http://private.invalid"),
                response=httpx.Response(404),
            ),
            UpstreamError,
        ),
        (
            httpx.HTTPStatusError(
                "secret response",
                request=httpx.Request("POST", "http://private.invalid"),
                response=httpx.Response(500),
            ),
            UpstreamError,
        ),
    ]
    original = n8n_module.httpx.AsyncClient
    try:
        for raised_error, expected_error in cases:
            class RaisingClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def post(self, *args, **kwargs):
                    raise raised_error

            n8n_module.httpx.AsyncClient = RaisingClient
            with pytest.raises(expected_error) as caught:
                await service.trigger_notification({"risk": {}})
            assert "private" not in str(caught.value)
            assert "secret" not in str(caught.value)
    finally:
        n8n_module.httpx.AsyncClient = original


async def test_n8n_service_fails_safely_when_config_is_missing():
    from app.config import Settings
    from app.services.n8n_service import N8nService

    settings = Settings(
        _env_file=None,
        N8N_NOTIFICATION_WEBHOOK_URL=None,
    )
    service = N8nService(settings)

    with pytest.raises(UpstreamConfigurationError) as caught:
        await service.trigger_notification({"risk": {}})

    assert caught.value.error_code == "n8n_config_missing"
    assert "http" not in str(caught.value)
