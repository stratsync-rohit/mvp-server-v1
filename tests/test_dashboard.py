from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from app.dependencies import get_dashboard_service
from app.main import app


pytestmark = pytest.mark.asyncio


async def test_dashboard_summary_zero_data(client):
    response = await client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "total_clients": 0,
            "active_teams_channels": 0,
            "inactive_channels": 0,
            "notifications_sent": 0,
        },
    }


async def test_dashboard_summary_counts_database_documents(client, mongo_db):
    await mongo_db["clients"].insert_many([
        {"name": "Client A", "code": "DASH-A", "is_active": True},
        {"name": "Client B", "code": "DASH-B", "is_active": False},
        {"name": "Client C", "code": "DASH-C", "is_active": True},
    ])
    await mongo_db["teams_channels"].insert_many([
        {"team_name": "A", "is_active": True},
        {"team_name": "B", "is_active": True},
        {"team_name": "C", "is_active": False},
        {"team_name": "Legacy without status"},
    ])
    await mongo_db["notifications"].insert_many([
        {"risk_id": "RISK-1", "status": "sent"},
        {"risk_id": "RISK-2", "status": "sent"},
        {"risk_id": "RISK-3", "status": "failed"},
        {"risk_id": "RISK-4", "status": "pending"},
    ])

    response = await client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "total_clients": 3,
            "active_teams_channels": 2,
            "inactive_channels": 1,
            "notifications_sent": 2,
        },
    }
    assert all(
        isinstance(value, int)
        for value in response.json()["data"].values()
    )


async def test_dashboard_summary_failure_returns_safe_500(client):
    service = AsyncMock()
    service.get_summary = AsyncMock(
        side_effect=RuntimeError(
            "mongodb://private-host and private webhook detail"
        )
    )
    app.dependency_overrides[get_dashboard_service] = lambda: service

    try:
        response = await client.get("/api/dashboard/summary")
    finally:
        app.dependency_overrides.pop(get_dashboard_service, None)

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Unable to fetch dashboard summary"
    }
    assert "private-host" not in response.text
    assert "webhook" not in response.text


async def test_client_dashboard_summary_is_scoped_and_counts_distinct_teams(
    client, mongo_db
):
    selected_id = ObjectId()
    other_id = ObjectId()
    await mongo_db["clients"].insert_many([
        {
            "_id": selected_id,
            "name": "Rohit test",
            "code": "ROH-001",
            "is_active": True,
        },
        {
            "_id": other_id,
            "name": "Other client",
            "code": "OTH-001",
            "is_active": True,
        },
    ])
    await mongo_db["teams_channels"].insert_many([
        {"client_id": selected_id, "team_name": "Operations", "is_active": True},
        {"client_id": selected_id, "team_name": "Operations", "is_active": True},
        {"client_id": selected_id, "team_name": "Management", "is_active": True},
        {"client_id": selected_id, "team_name": "Legacy", "is_active": False},
        {"client_id": other_id, "team_name": "Other", "is_active": True},
    ])
    await mongo_db["notifications"].insert_many([
        {"client_id": selected_id, "status": "sent"},
        {"client_id": selected_id, "status": "failed"},
        {"client_id": other_id, "status": "sent"},
    ])

    response = await client.get(
        "/api/dashboard/summary",
        params={"client_id": str(selected_id)},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "client": {
                "id": str(selected_id),
                "name": "Rohit test",
                "code": "ROH-001",
                "is_active": True,
            },
            "active_teams": 2,
            "active_teams_channels": 3,
            "inactive_channels": 1,
            "notifications_sent": 1,
        },
    }


@pytest.mark.parametrize("client_id", ["not-an-object-id", str(ObjectId())])
async def test_client_dashboard_summary_missing_client_returns_404(client, client_id):
    response = await client.get(
        "/api/dashboard/summary",
        params={"client_id": client_id},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Client not found"}


async def test_recent_integrations_returns_only_safe_metadata(client, mongo_db):
    client_id = ObjectId()
    destination_id = ObjectId()
    await mongo_db["clients"].insert_one({
        "_id": client_id,
        "name": "Safe Client",
        "code": "SAF-001",
        "is_active": True,
    })
    await mongo_db["teams_channels"].insert_one({
        "_id": destination_id,
        "client_id": client_id,
        "team_name": "Operations",
        "channel_name": "Risk Alerts",
        "teams_webhook_url": "https://example.com/SECRET",
        "tenant_id": "private-tenant",
        "team_id": "private-team",
        "channel_id": "private-channel",
        "is_active": True,
    })

    response = await client.get("/api/dashboard/recent-integrations")

    assert response.status_code == 200
    data = response.json()["data"][0]
    assert data == {
        "id": str(destination_id),
        "client_id": str(client_id),
        "client_name": "Safe Client",
        "team_name": "Operations",
        "channel_name": "Risk Alerts",
        "is_active": True,
        "webhook_configured": True,
        "created_at": None,
    }
    assert "SECRET" not in response.text
    assert "private-tenant" not in response.text
