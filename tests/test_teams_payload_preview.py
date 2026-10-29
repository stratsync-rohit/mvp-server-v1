from copy import deepcopy

import pytest

from app.repositories.risk_repository import RiskRepository
from app.services.notification_service import NotificationService
from app.services.teams_card_renderer import build_teams_notification_payload
from app.services.teams_payload_preview_service import (
    TeamsPayloadPreviewService,
)
from app.utils.payload_size import utf8_json_size_bytes


pytestmark = pytest.mark.asyncio


def _risk_payload(risk_id: str = "RSK-PREVIEW-001"):
    return {
        "risk_id": risk_id,
        "industry_slug": "distribution-trading",
        "industry_name": "Distribution & Trading",
        "title": "Supplier delivery disruption",
        "severity": "high",
        "severity_label": "High",
        "summary": "Delivery dates are at risk.",
        "sender": {"name": "StratSync", "source": "Risk Monitor"},
        "entity": {
            "type": "supplier",
            "id": "SUP-42",
            "name": "Example Supplier",
        },
    }


def _notification_service(mongo_db):
    return NotificationService(
        notification_repository=None,
        risk_repository=RiskRepository(mongo_db),
        teams_channel_repository=None,
        slack_destination_repository=None,
        client_repository=None,
        risk_destination_override_service=None,
        n8n_service=None,
        slack_n8n_service=None,
    )


async def test_preview_size_returns_rendered_payload_measurement(client):
    response = await client.post(
        "/api/notifications/preview-size",
        json={"risk": _risk_payload()},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["bytes"], int)
    assert isinstance(body["kb"], float)
    assert body["limit_bytes"] == 28 * 1024
    assert body["limit_kb"] == 28
    assert body["too_large"] is False
    assert body["measurement"] == "rendered-teams-payload"


async def test_preview_size_uses_exact_notification_rendering_path(mongo_db):
    risk = _risk_payload()
    service = _notification_service(mongo_db)

    renderer_risk = await service.prepare_notification_risk_payload(risk)
    expected_payload = build_teams_notification_payload(renderer_risk)
    preview = await TeamsPayloadPreviewService(service).preview_size(risk)

    assert preview["bytes"] == utf8_json_size_bytes(expected_payload)


async def test_preview_size_measures_utf8_multibyte_content(client):
    ascii_risk = _risk_payload("RSK-PREVIEW-ASCII")
    unicode_risk = _risk_payload("RSK-PREVIEW-UNICODE")
    unicode_risk["summary"] = "₹ जोखिम — 供应商延误"

    ascii_response = await client.post(
        "/api/notifications/preview-size", json={"risk": ascii_risk}
    )
    unicode_response = await client.post(
        "/api/notifications/preview-size", json={"risk": unicode_risk}
    )

    assert unicode_response.status_code == 200
    assert unicode_response.json()["bytes"] > ascii_response.json()["bytes"]
    assert utf8_json_size_bytes({"text": "₹"}) == len(
        b'{"text":"\xe2\x82\xb9"}'
    )


async def test_preview_size_enriches_connected_risks_like_notification(
    client,
    mongo_db,
):
    associated_risk = _risk_payload("RSK-PREVIEW-ASSOCIATED")
    associated_risk.update(
        {
            "title": "Warehouse stockout",
            "severity": "critical",
            "severity_label": "Critical",
            "metadata": {"primary_exposure": "US$250,000"},
        }
    )
    await mongo_db["risks"].insert_one(associated_risk)

    risk = _risk_payload()
    risk["associated_risk_ids"] = ["RSK-PREVIEW-ASSOCIATED"]
    response = await client.post(
        "/api/notifications/preview-size", json={"risk": risk}
    )

    prepared = await _notification_service(mongo_db).prepare_notification_risk_payload(
        risk
    )
    assert response.status_code == 200
    assert prepared["connected_risk_overview"] == [
        {
            "risk_id": "RSK-PREVIEW-ASSOCIATED",
            "risk": "Warehouse stockout",
            "severity": "Critical",
            "primary_exposure": "US$250,000",
        }
    ]


async def test_preview_size_includes_showcards_blocks_and_oversize_status(client):
    base = _risk_payload("RSK-PREVIEW-BASE")
    detailed = _risk_payload("RSK-PREVIEW-DETAILED")
    detailed["details"] = {
        "section_title": "DETAILS",
        "items": [{"label": "Exposure", "value": "US$250,000"}],
    }
    detailed["mitigation"] = {
        "summary": "Reduce exposure.",
        "steps": [
            {
                "step": 1,
                "title": "Contact supplier",
                "owner": "Procurement",
            }
        ],
        "last_updated": "2026-10-28T00:00:00Z",
        "next_action": "Confirm alternate supply.",
    }

    base_response = await client.post(
        "/api/notifications/preview-size", json={"risk": base}
    )
    detailed_response = await client.post(
        "/api/notifications/preview-size", json={"risk": detailed}
    )
    assert detailed_response.json()["bytes"] > base_response.json()["bytes"]

    oversized = _risk_payload("RSK-PREVIEW-OVERSIZED")
    oversized["summary"] = "危険" * 20_000
    oversized_response = await client.post(
        "/api/notifications/preview-size", json={"risk": oversized}
    )
    assert oversized_response.status_code == 200
    assert oversized_response.json()["too_large"] is True


async def test_preview_size_includes_v2_notification_blocks_and_saved_risks(
    client,
    mongo_db,
):
    saved_risk = _risk_payload("RSK-PREVIEW-SAVED")
    await mongo_db["risks"].insert_one(deepcopy(saved_risk))

    base_v2 = deepcopy(saved_risk)
    base_v2["schema_version"] = 2
    base_v2["views"] = {"notification": {"blocks": []}}
    blocks_v2 = deepcopy(base_v2)
    blocks_v2["risk_id"] = "RSK-PREVIEW-BLOCKS"
    blocks_v2["views"]["notification"]["blocks"] = [
        {"type": "text", "text": "Additional rendered notification content."}
    ]

    saved_response = await client.post(
        "/api/notifications/preview-size", json={"risk": saved_risk}
    )
    base_response = await client.post(
        "/api/notifications/preview-size", json={"risk": base_v2}
    )
    blocks_response = await client.post(
        "/api/notifications/preview-size", json={"risk": blocks_v2}
    )

    assert saved_response.status_code == 200
    assert blocks_response.json()["bytes"] > base_response.json()["bytes"]


async def test_preview_size_handles_missing_associated_risks_like_delivery(
    client,
    mongo_db,
):
    risk = _risk_payload()
    risk["associated_risk_ids"] = ["RSK-PREVIEW-MISSING"]

    response = await client.post(
        "/api/notifications/preview-size", json={"risk": risk}
    )
    prepared = await _notification_service(mongo_db).prepare_notification_risk_payload(
        risk
    )

    assert response.status_code == 200
    assert prepared["connected_risk_overview"] == []


async def test_preview_size_never_calls_the_teams_webhook(client, monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("Preview must not send a Teams webhook")

    monkeypatch.setattr(
        "app.services.teams_webhook_service.TeamsWebhookService.send",
        fail_if_called,
    )

    response = await client.post(
        "/api/notifications/preview-size", json={"risk": _risk_payload()}
    )

    assert response.status_code == 200


async def test_preview_size_has_no_persistence_or_delivery_side_effects(
    client,
    mongo_db,
):
    risk = _risk_payload()
    original_risk = deepcopy(risk)
    before_risk_count = await mongo_db["risks"].count_documents({})
    before_notification_count = await mongo_db["notifications"].count_documents({})

    response = await client.post(
        "/api/notifications/preview-size", json={"risk": risk}
    )

    assert response.status_code == 200
    assert risk == original_risk
    assert await mongo_db["risks"].count_documents({}) == before_risk_count
    assert await mongo_db["notifications"].count_documents({}) == (
        before_notification_count
    )


async def test_preview_size_rejects_invalid_risk_payload(client):
    response = await client.post(
        "/api/notifications/preview-size",
        json={"risk": {"risk_id": "RSK-PREVIEW-INVALID"}},
    )

    assert response.status_code == 422
