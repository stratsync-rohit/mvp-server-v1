import hashlib
import hmac
import json
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest

from app.api import slack_interactions as interactions_api
from app.config import Settings, get_settings
from app.dependencies import get_risk_service
from app.main import app
from app.services import slack_signature_service


pytestmark = pytest.mark.asyncio


TEST_SIGNING_SECRET = "test-slack-signing-secret"
TEST_TIMESTAMP = 1_700_000_000


@pytest.fixture(autouse=True)
def fixed_slack_timestamp(monkeypatch):
    monkeypatch.setattr(
        slack_signature_service.time,
        "time",
        lambda: TEST_TIMESTAMP,
    )


def _interaction(view: str = "details") -> dict:
    action_id = {
        "details": "risk_view_details",
        "mitigation": "risk_view_mitigation",
    }[view]
    return {
        "type": "block_actions",
        "actions": [
            {
                "action_id": action_id,
                "value": json.dumps(
                    {"risk_id": "RSK-TEST-001", "view": view},
                    separators=(",", ":"),
                ),
            }
        ],
        "response_url": "https://hooks.slack.com/response/test",
    }


def _signed_body_and_headers(
    interaction: dict,
    timestamp: int = TEST_TIMESTAMP,
) -> tuple[bytes, dict[str, str]]:
    payload = json.dumps(interaction, separators=(",", ":"))
    raw_body = urlencode({"payload": payload}).encode("utf-8")
    timestamp_text = str(timestamp)
    signature_base = (
        b"v0:" + timestamp_text.encode("utf-8") + b":" + raw_body
    )
    signature = "v0=" + hmac.new(
        TEST_SIGNING_SECRET.encode("utf-8"),
        signature_base,
        hashlib.sha256,
    ).hexdigest()
    return raw_body, {
        "content-type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": timestamp_text,
        "X-Slack-Signature": signature,
    }


@pytest.fixture
def interaction_dependencies():
    service = AsyncMock()
    service.get_risk_by_id.return_value = {"risk_id": "RSK-TEST-001"}
    settings = Settings.model_construct(
        slack_signing_secret=TEST_SIGNING_SECRET,
    )
    app.dependency_overrides[get_risk_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: settings
    return service


async def test_valid_slack_signature_reaches_existing_handler(
    client,
    interaction_dependencies,
    monkeypatch,
):
    service = interaction_dependencies
    response_sender = AsyncMock()
    monkeypatch.setattr(
        interactions_api,
        "_send_slack_response",
        response_sender,
    )
    monkeypatch.setattr(
        interactions_api,
        "build_slack_risk_view_payload",
        lambda risk, view: {"text": view, "blocks": []},
    )
    raw_body, headers = _signed_body_and_headers(_interaction("details"))

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "risk_id": "RSK-TEST-001",
        "view": "details",
    }
    service.get_risk_by_id.assert_awaited_once_with("RSK-TEST-001")
    response_sender.assert_awaited_once()


@pytest.mark.parametrize("view", ["details", "mitigation"])
async def test_existing_slack_views_work_with_valid_signature(
    client,
    interaction_dependencies,
    monkeypatch,
    view,
):
    response_sender = AsyncMock()
    monkeypatch.setattr(
        interactions_api,
        "_send_slack_response",
        response_sender,
    )
    monkeypatch.setattr(
        interactions_api,
        "build_slack_risk_view_payload",
        lambda risk, requested_view: {"text": requested_view, "blocks": []},
    )
    raw_body, headers = _signed_body_and_headers(_interaction(view))

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["view"] == view


async def test_invalid_signature_returns_401_without_running_business_logic(
    client,
    interaction_dependencies,
):
    service = interaction_dependencies
    raw_body, headers = _signed_body_and_headers(_interaction())
    headers["X-Slack-Signature"] = "v0=" + ("0" * 64)

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Slack signature"}
    service.get_risk_by_id.assert_not_awaited()


@pytest.mark.parametrize(
    "missing_header",
    ["X-Slack-Signature", "X-Slack-Request-Timestamp"],
)
async def test_missing_slack_signature_headers_return_401(
    client,
    interaction_dependencies,
    missing_header,
):
    raw_body, headers = _signed_body_and_headers(_interaction())
    headers.pop(missing_header)

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 401


async def test_malformed_timestamp_returns_401(
    client,
    interaction_dependencies,
):
    raw_body, headers = _signed_body_and_headers(_interaction())
    headers["X-Slack-Request-Timestamp"] = "not-a-timestamp"

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "timestamp",
    [TEST_TIMESTAMP - 301, TEST_TIMESTAMP + 301],
)
async def test_stale_or_future_timestamp_returns_401(
    client,
    interaction_dependencies,
    monkeypatch,
    timestamp,
):
    monkeypatch.setattr(
        slack_signature_service.time,
        "time",
        lambda: TEST_TIMESTAMP,
    )
    raw_body, headers = _signed_body_and_headers(
        _interaction(),
        timestamp=timestamp,
    )

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 401


async def test_signature_uses_exact_raw_request_body(
    client,
    interaction_dependencies,
    monkeypatch,
):
    response_sender = AsyncMock()
    monkeypatch.setattr(
        interactions_api,
        "_send_slack_response",
        response_sender,
    )
    monkeypatch.setattr(
        interactions_api,
        "build_slack_risk_view_payload",
        lambda risk, view: {"text": view, "blocks": []},
    )
    raw_body, headers = _signed_body_and_headers(_interaction())

    valid_response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )
    modified_response = await client.post(
        "/api/slack/interactions",
        content=raw_body + b"&extra=modified",
        headers=headers,
    )

    assert valid_response.status_code == 200
    assert modified_response.status_code == 401


async def test_missing_signing_secret_fails_safely(
    client,
    interaction_dependencies,
):
    app.dependency_overrides[get_settings] = lambda: Settings.model_construct(
        slack_signing_secret=None,
    )
    raw_body, headers = _signed_body_and_headers(_interaction())

    response = await client.post(
        "/api/slack/interactions",
        content=raw_body,
        headers=headers,
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Slack request verification is not configured"
    }
