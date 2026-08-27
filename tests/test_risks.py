from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from bson import ObjectId


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def risk_data(mongo_db):
    now = datetime.now(timezone.utc)
    await mongo_db["industries"].insert_many([
        {
            "slug": "distribution-trading",
            "name": "Distribution & Trading",
            "is_active": True,
        },
        {
            "slug": "ship-management",
            "name": "Ship Management",
            "is_active": True,
        },
        {
            "slug": "inactive-industry",
            "name": "Inactive Industry",
            "is_active": True,
        },
    ])
    documents = [
        {
            "risk_id": "TEST-DIST-HIGH",
            "card_id": "supplier-reliability",
            "industry_slug": "distribution-trading",
            "industry_name": "Distribution & Trading",
            "title": "Supplier reliability changed",
            "severity": "high",
            "metrics": [{"label": "Exposure", "value": "$84,000"}],
            "details": {"supplier": "Supplier A3"},
            "supplier_comparison": [{"supplier": "Supplier A1"}],
            "mitigation": [{"step": 1, "owner": "Procurement"}],
            "related_document_id": ObjectId(),
            "is_active": True,
            "created_at": now,
        },
        {
            "risk_id": "TEST-DIST-LOW",
            "industry_slug": "distribution-trading",
            "industry_name": "Distribution & Trading",
            "title": "Cover position changed",
            "severity": "low",
            "metrics": [],
            "details": {},
            "mitigation": {},
            "is_active": True,
            "created_at": now - timedelta(minutes=1),
        },
        {
            "risk_id": "TEST-SHIP-CRITICAL",
            "industry_slug": "ship-management",
            "industry_name": "Ship Management",
            "title": "Dry dock budget changed",
            "severity": "critical",
            "financial_details": {"budget_overrun": "US$270,000"},
            "assign": {"current_owner": "Unassigned"},
            "is_active": True,
            "created_at": now - timedelta(minutes=2),
        },
        {
            "risk_id": "TEST-INACTIVE-ONLY",
            "industry_slug": "inactive-industry",
            "industry_name": "Inactive Industry",
            "title": "Inactive risk",
            "severity": "high",
            "is_active": False,
            "created_at": now - timedelta(minutes=3),
        },
    ]
    result = await mongo_db["risks"].insert_many(documents)
    return {"documents": documents, "ids": result.inserted_ids}


async def test_get_industries_success(client, risk_data):
    response = await client.get("/api/industries")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert len(response.json()["data"]) == 3


async def test_get_industries_are_unique_and_counts_are_correct(
    client, risk_data
):
    response = await client.get("/api/industries")
    industries = {
        industry["slug"]: industry
        for industry in response.json()["data"]
    }

    assert set(industries) == {
        "distribution-trading",
        "ship-management",
        "inactive-industry",
    }
    assert industries["distribution-trading"]["risk_count"] == 2
    assert industries["ship-management"]["risk_count"] == 1
    assert industries["inactive-industry"]["risk_count"] == 0


async def test_get_industry_risks_success(client, risk_data):
    response = await client.get(
        "/api/industries/distribution-trading/risks"
    )

    assert response.status_code == 200
    risks = response.json()["data"]
    assert [risk["risk_id"] for risk in risks] == [
        "TEST-DIST-HIGH",
        "TEST-DIST-LOW",
    ]
    assert all(risk["industry_slug"] == "distribution-trading" for risk in risks)


async def test_inactive_industry_exists_but_has_no_active_risks(
    client, risk_data
):
    response = await client.get("/api/industries/inactive-industry/risks")

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_get_unknown_industry_returns_404(client, risk_data):
    response = await client.get("/api/industries/does-not-exist/risks")

    assert response.status_code == 404
    assert response.json() == {"detail": "Industry not found"}


async def test_get_all_risks_returns_active_risks(client, risk_data):
    response = await client.get("/api/risks")

    assert response.status_code == 200
    risk_ids = {risk["risk_id"] for risk in response.json()["data"]}
    assert "TEST-DIST-HIGH" in risk_ids
    assert "TEST-SHIP-CRITICAL" in risk_ids
    assert "TEST-INACTIVE-ONLY" not in risk_ids


async def test_get_risks_filters_by_industry(client, risk_data):
    response = await client.get(
        "/api/risks", params={"industry_slug": "ship-management"}
    )

    assert response.status_code == 200
    risks = response.json()["data"]
    assert [risk["risk_id"] for risk in risks] == ["TEST-SHIP-CRITICAL"]


async def test_get_risks_filters_by_severity(client, risk_data):
    response = await client.get("/api/risks", params={"severity": "critical"})

    assert response.status_code == 200
    risks = response.json()["data"]
    assert [risk["risk_id"] for risk in risks] == ["TEST-SHIP-CRITICAL"]


async def test_get_risks_filters_by_active_status(client, risk_data):
    response = await client.get("/api/risks", params={"is_active": "false"})

    assert response.status_code == 200
    assert [risk["risk_id"] for risk in response.json()["data"]] == [
        "TEST-INACTIVE-ONLY"
    ]


async def test_get_risk_by_business_id_preserves_complete_document(
    client, risk_data
):
    response = await client.get("/api/risks/TEST-DIST-HIGH")

    assert response.status_code == 200
    risk = response.json()["data"]
    assert risk["risk_id"] == "TEST-DIST-HIGH"
    assert risk["card_id"] == "supplier-reliability"
    assert risk["metrics"][0]["value"] == "$84,000"
    assert risk["details"] == {"supplier": "Supplier A3"}
    assert risk["supplier_comparison"] == [{"supplier": "Supplier A1"}]
    assert risk["mitigation"] == [{"step": 1, "owner": "Procurement"}]
    assert "id" in risk
    assert "_id" not in risk
    assert isinstance(risk["related_document_id"], str)


async def test_get_unknown_risk_returns_404(client, risk_data):
    response = await client.get("/api/risks/UNKNOWN-RISK")

    assert response.status_code == 404
    assert response.json() == {"detail": "Risk not found"}
