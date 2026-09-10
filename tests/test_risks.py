from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from bson import ObjectId


pytestmark = pytest.mark.asyncio


@pytest.fixture
def canonical_risk_payload():
    return {
        "risk_id": "RSK-V22U-OZVV",
        "card_id": "revenue-to-cover",
        "industry_slug": "distribution-trading",
        "industry_name": "Distribution & Trading",
        "title": "Potential To-Cover Risk Discovered",
        "severity": "high",
        "severity_label": "High",
        "subtitle": "SKU 21132 · Burberry XYZ Perfume for Men",
        "summary": "Pending sales orders have increased...",
        "sender": {
            "name": "StratSync Risk Monitor",
            "source": "Potential To-Cover Alert",
            "risk_id": "MISMATCHED-ID",
            "timestamp": "09:42 AM IST",
        },
        "entity": {
            "type": "sku",
            "id": "21132",
            "name": "Burberry XYZ Perfume for Men",
        },
        "metrics": [
            {
                "key": "revenue_at_risk",
                "label": "Revenue at Risk",
                "value": "$130,000",
                "raw_value": 130000,
                "type": "currency",
                "highlight": True,
            }
        ],
        "details": {
            "section_title": "ITEM-LEVEL DETAILS",
            "items": [
                {
                    "label": "Demand signal",
                    "value": "Pending sales orders exceed available inventory.",
                }
            ],
            "underlying_exposure": [
                "Pending sales orders exceed available inventory."
            ],
            "impact": [
                "Open customer orders may miss requested delivery dates."
            ],
        },
        "mitigation": {
            "summary": "Close the cover gap.",
            "steps": [
                {
                    "step": 4,
                    "title": "Confirm cover gap",
                    "description": "Validate current stock and demand.",
                    "owner": "Procurement",
                },
                {
                    "step": 5,
                    "title": "New mitigation step",
                    "description": "",
                    "owner": "",
                },
                {
                    "step": 8,
                    "title": "Expedite replenishment",
                    "description": "Request an expedited delivery.",
                    "owner": "Supply Chain",
                },
            ],
            "last_updated": "2026-08-27T04:01:55.261Z",
            "next_action": "Confirm the cover gap with Procurement.",
        },
        "actions": [],
        "detected_time": "09:42 AM IST",
        "is_active": True,
        "status": "active",
    }


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


async def test_create_canonical_risk(client, mongo_db, canonical_risk_payload):
    response = await client.post("/api/risks", json=canonical_risk_payload)

    assert response.status_code == 201
    assert response.json()["message"] == "Risk created successfully"
    assert response.json()["risk_id"] == canonical_risk_payload["risk_id"]
    assert isinstance(response.json()["_id"], str)

    stored = await mongo_db["risks"].find_one(
        {"risk_id": canonical_risk_payload["risk_id"]}
    )
    assert stored["_id"] is not None
    assert isinstance(stored["created_at"], datetime)
    assert isinstance(stored["updated_at"], datetime)
    assert stored["created_at"] == stored["updated_at"]
    assert stored["sender"]["risk_id"] == stored["risk_id"]
    assert stored["entity"] == canonical_risk_payload["entity"]
    assert stored["sender"]["source"] == "Potential To-Cover Alert"
    assert stored["details"]["section_title"] == "ITEM-LEVEL DETAILS"

    steps = stored["mitigation"]["steps"]
    assert [step["title"] for step in steps] == [
        "Confirm cover gap",
        "Expedite replenishment",
    ]
    assert [step["step"] for step in steps] == [1, 2]


async def test_create_risk_without_sender_id_normalizes_it(
    client, mongo_db, canonical_risk_payload
):
    canonical_risk_payload["risk_id"] = "RSK-NO-SENDER-ID"
    canonical_risk_payload["sender"].pop("risk_id")

    response = await client.post("/api/risks", json=canonical_risk_payload)

    assert response.status_code == 201
    stored = await mongo_db["risks"].find_one({"risk_id": "RSK-NO-SENDER-ID"})
    assert stored["sender"]["risk_id"] == "RSK-NO-SENDER-ID"


async def test_create_duplicate_risk_returns_409(
    client, canonical_risk_payload
):
    first = await client.post("/api/risks", json=canonical_risk_payload)
    duplicate = await client.post("/api/risks", json=canonical_risk_payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Risk ID already exists"}


@pytest.mark.parametrize("risk_id", [None, "", "   "])
async def test_create_risk_requires_non_blank_risk_id(
    client, canonical_risk_payload, risk_id
):
    if risk_id is None:
        canonical_risk_payload.pop("risk_id")
    else:
        canonical_risk_payload["risk_id"] = risk_id

    response = await client.post("/api/risks", json=canonical_risk_payload)

    assert response.status_code == 422


async def test_update_canonical_risk_preserves_identity_and_cleans_steps(
    client, mongo_db, canonical_risk_payload
):
    created = await client.post("/api/risks", json=canonical_risk_payload)
    assert created.status_code == 201
    before = await mongo_db["risks"].find_one(
        {"risk_id": canonical_risk_payload["risk_id"]}
    )

    canonical_risk_payload["title"] = "Updated risk title"
    canonical_risk_payload["sender"]["risk_id"] = "WRONG-SENDER-ID"
    canonical_risk_payload["mitigation"]["steps"] = [
        {
            "step": 9,
            "title": "New mitigation step",
            "description": "",
            "owner": "",
        },
        {
            "step": 12,
            "title": "Review supplier options",
            "description": "Compare available suppliers.",
            "owner": "Procurement",
        },
    ]
    canonical_risk_payload["_id"] = "client-controlled-id"
    canonical_risk_payload["created_at"] = "2000-01-01T00:00:00Z"

    response = await client.put(
        f"/api/risks/{canonical_risk_payload['risk_id']}",
        json=canonical_risk_payload,
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Risk updated successfully",
        "risk_id": canonical_risk_payload["risk_id"],
    }
    stored = await mongo_db["risks"].find_one(
        {"risk_id": canonical_risk_payload["risk_id"]}
    )
    assert stored["_id"] == before["_id"]
    assert stored["created_at"] == before["created_at"]
    assert stored["updated_at"] >= before["updated_at"]
    assert stored["title"] == "Updated risk title"
    assert stored["sender"]["risk_id"] == stored["risk_id"]
    assert stored["mitigation"]["steps"] == [
        {
            "step": 1,
            "title": "Review supplier options",
            "description": "Compare available suppliers.",
            "owner": "Procurement",
        }
    ]


async def test_update_rejects_risk_id_change(client, canonical_risk_payload):
    created = await client.post("/api/risks", json=canonical_risk_payload)
    assert created.status_code == 201
    original_id = canonical_risk_payload["risk_id"]
    canonical_risk_payload["risk_id"] = "RSK-DIFFERENT-ID"

    response = await client.put(
        f"/api/risks/{original_id}", json=canonical_risk_payload
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Risk ID cannot be changed"}


async def test_update_unknown_risk_returns_404(client, canonical_risk_payload):
    canonical_risk_payload["risk_id"] = "RSK-UNKNOWN-EDIT"

    response = await client.put(
        "/api/risks/RSK-UNKNOWN-EDIT", json=canonical_risk_payload
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Risk not found"}


async def test_delete_risk_only_deletes_requested_document(
    client, mongo_db, canonical_risk_payload
):
    created = await client.post("/api/risks", json=canonical_risk_payload)
    assert created.status_code == 201
    await mongo_db["notifications"].insert_one(
        {"risk_id": canonical_risk_payload["risk_id"], "status": "sent"}
    )

    response = await client.delete(
        f"/api/risks/{canonical_risk_payload['risk_id']}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Risk deleted successfully",
        "risk_id": canonical_risk_payload["risk_id"],
    }
    assert await mongo_db["risks"].find_one(
        {"risk_id": canonical_risk_payload["risk_id"]}
    ) is None
    assert await mongo_db["risks"].find_one(
        {"risk_id": "RSK-21132-0472"}
    ) is not None
    assert await mongo_db["notifications"].find_one(
        {"risk_id": canonical_risk_payload["risk_id"]}
    ) is not None


async def test_delete_unknown_risk_returns_404(client):
    response = await client.delete("/api/risks/RSK-UNKNOWN-DELETE")

    assert response.status_code == 404
    assert response.json() == {"detail": "Risk not found"}
