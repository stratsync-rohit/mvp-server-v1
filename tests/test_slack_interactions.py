import hashlib
import hmac
import json
import time
from urllib.parse import quote_plus, urlencode
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.api.slack_interactions import receive_slack_interaction
from app.config import Settings
from app.dependencies import get_slack_interaction_n8n_service
from app.exceptions import (
    SlackInteractionConfigurationError,
    UpstreamError,
    UpstreamTimeoutError,
)
from app.services.slack_interaction_service import SlackInteractionService
from tests.conftest import TEST_SLACK_SIGNING_SECRET


pytestmark = pytest.mark.asyncio

INTERACTION_PATH = "/api/slack/interactions"
RESPONSE_URL = "https://hooks.slack.com/actions/T000/B000/private-response"
INTERNAL_N8N_URL = "https://n8n.internal.example/webhook/slack-interaction"


def _interaction_payload(
    action="view_details",
    risk_id="RSK-DD-0904",
    response_url=RESPONSE_URL,
    channel_name="risk-alerts",
):
    return {
        "type": "block_actions",
        "actions": [
            {
                "action_id": action,
                "value": json.dumps(
                    {"riskId": risk_id, "actionKey": action},
                    separators=(",", ":"),
                ),
            }
        ],
        "response_url": response_url,
        "user": {"id": "U123"},
        "channel": {"id": "C123", "name": channel_name},
    }


def _body(payload=None):
    data = _interaction_payload() if payload is None else payload
    return urlencode(
        {"payload": json.dumps(data, separators=(",", ":"))}
    ).encode()


def _signature(body, timestamp):
    signature_base = b"v0:" + str(timestamp).encode() + b":" + body
    digest = hmac.new(
        TEST_SLACK_SIGNING_SECRET.encode(),
        signature_base,
        hashlib.sha256,
    ).hexdigest()
    return f"v0={digest}"


def _headers(body, timestamp=None, signature=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": str(timestamp),
        "X-Slack-Signature": signature or _signature(body, timestamp),
    }


async def _post(client, body, **header_overrides):
    headers = _headers(body)
    headers.update(header_overrides)
    return await client.post(INTERACTION_PATH, content=body, headers=headers)


@pytest.mark.parametrize("action", ["view_details", "mitigation_plan"])
async def test_valid_supported_interactions_are_acked_and_normalized(
    client, mock_slack_interaction_n8n_service, action
):
    body = _body(_interaction_payload(action=action))

    response = await _post(client, body)

    assert response.status_code == 200
    assert response.content == b""
    mock_slack_interaction_n8n_service.trigger_notification.assert_awaited_once_with(
        {
            "platform": "slack",
            "interaction_type": "block_action",
            "riskId": "RSK-DD-0904",
            "actionKey": action,
            "actionId": action,
            "responseUrl": RESPONSE_URL,
            "userId": "U123",
            "channelId": "C123",
            "channelName": "risk-alerts",
        }
    )
    assert RESPONSE_URL not in response.text


async def test_signature_uses_exact_raw_request_body(
    client, mock_slack_interaction_n8n_service
):
    payload_json = json.dumps(_interaction_payload(), separators=(",", ":"))
    body = f"payload={quote_plus(payload_json, safe='/')}".encode()
    timestamp = int(time.time())

    response = await client.post(
        INTERACTION_PATH,
        content=body,
        headers=_headers(body, timestamp=timestamp),
    )

    assert response.status_code == 200
    mock_slack_interaction_n8n_service.trigger_notification.assert_awaited_once()

    differently_encoded = urlencode({"payload": payload_json}).encode()
    rejected = await client.post(
        INTERACTION_PATH,
        content=differently_encoded,
        headers=_headers(body, timestamp=timestamp),
    )
    assert rejected.status_code == 401


async def test_invalid_signature_is_rejected(client):
    body = _body()
    response = await _post(
        client,
        body,
        **{"X-Slack-Signature": "v0=invalid"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Slack request signature"}


async def test_missing_signature_is_rejected(client):
    body = _body()
    headers = _headers(body)
    headers.pop("X-Slack-Signature")
    response = await client.post(INTERACTION_PATH, content=body, headers=headers)
    assert response.status_code == 401


async def test_missing_timestamp_is_rejected(client):
    body = _body()
    headers = _headers(body)
    headers.pop("X-Slack-Request-Timestamp")
    response = await client.post(INTERACTION_PATH, content=body, headers=headers)
    assert response.status_code == 401


async def test_invalid_timestamp_is_rejected(client):
    body = _body()
    response = await client.post(
        INTERACTION_PATH,
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": "not-a-timestamp",
            "X-Slack-Signature": "v0=irrelevant",
        },
    )
    assert response.status_code == 401


async def test_timestamp_older_than_five_minutes_is_rejected(client):
    body = _body()
    timestamp = int(time.time()) - 301
    response = await client.post(
        INTERACTION_PATH,
        content=body,
        headers=_headers(body, timestamp=timestamp),
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"type": "block_actions", "actions": []},
        {"type": "not_block_actions", "actions": []},
    ],
)
async def test_malformed_payload_is_rejected(client, payload):
    body = b"payload=not-json" if payload is None else _body(payload)
    response = await _post(client, body)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Slack interaction payload"}


async def test_malformed_button_value_is_rejected(client):
    payload = _interaction_payload()
    payload["actions"][0]["value"] = "not-json"
    response = await _post(client, _body(payload))
    assert response.status_code == 400


async def test_unsupported_action_is_rejected(client):
    payload = _interaction_payload(action="delete_risk")
    response = await _post(client, _body(payload))
    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported Slack interaction action"}


async def test_mismatched_action_key_is_rejected(client):
    payload = _interaction_payload()
    payload["actions"][0]["value"] = json.dumps(
        {"riskId": "RSK-DD-0904", "actionKey": "mitigation_plan"}
    )
    response = await _post(client, _body(payload))
    assert response.status_code == 400


async def test_missing_risk_id_is_rejected(client):
    payload = _interaction_payload()
    payload["actions"][0]["value"] = json.dumps(
        {"actionKey": "view_details"}
    )
    response = await _post(client, _body(payload))
    assert response.status_code == 400


async def test_missing_response_url_is_rejected(client):
    payload = _interaction_payload()
    payload.pop("response_url")
    response = await _post(client, _body(payload))
    assert response.status_code == 400


async def test_missing_channel_name_is_forwarded_as_null(
    client, mock_slack_interaction_n8n_service
):
    body = _body(_interaction_payload(channel_name=None))
    response = await _post(client, body)
    assert response.status_code == 200
    forwarded = (
        mock_slack_interaction_n8n_service.trigger_notification.call_args.args[0]
    )
    assert forwarded["channelName"] is None


async def test_ack_schedules_forward_without_awaiting_it():
    body = _body()
    headers = _headers(body)
    scope = {
        "type": "http",
        "method": "POST",
        "path": INTERACTION_PATH,
        "headers": [
            (key.lower().encode(), value.encode())
            for key, value in headers.items()
        ],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive)
    background_tasks = BackgroundTasks()
    interaction_service = SlackInteractionService(
        Settings(
            _env_file=None,
            SLACK_SIGNING_SECRET=TEST_SLACK_SIGNING_SECRET,
        )
    )
    n8n_service = AsyncMock()
    n8n_service.trigger_notification = AsyncMock()

    response = await receive_slack_interaction(
        request=request,
        background_tasks=background_tasks,
        interaction_service=interaction_service,
        n8n_service=n8n_service,
    )

    assert response.status_code == 200
    n8n_service.trigger_notification.assert_not_awaited()
    assert len(background_tasks.tasks) == 1


@pytest.mark.parametrize(
    "upstream_error",
    [
        UpstreamTimeoutError("private timeout"),
        UpstreamError("private non-2xx", http_status=500),
    ],
)
async def test_n8n_failure_after_ack_is_safely_logged(
    client,
    mock_slack_interaction_n8n_service,
    caplog,
    upstream_error,
):
    mock_slack_interaction_n8n_service.trigger_notification.side_effect = (
        upstream_error
    )
    body = _body()
    signature = _headers(body)["X-Slack-Signature"]

    response = await _post(client, body)

    assert response.status_code == 200
    assert response.content == b""
    assert "slack_interaction_forward_failed" in caplog.text
    for sensitive_value in (
        TEST_SLACK_SIGNING_SECRET,
        signature,
        RESPONSE_URL,
        body.decode(),
        INTERNAL_N8N_URL,
    ):
        assert sensitive_value not in caplog.text


async def test_interaction_n8n_dependency_uses_dedicated_url():
    settings = Settings(
        _env_file=None,
        SLACK_INTERACTION_N8N_URL=INTERNAL_N8N_URL,
    )
    service = get_slack_interaction_n8n_service(settings)
    assert service.webhook_url == INTERNAL_N8N_URL


async def test_missing_signing_secret_fails_safely():
    service = SlackInteractionService(
        Settings(_env_file=None, SLACK_SIGNING_SECRET=None)
    )
    with pytest.raises(SlackInteractionConfigurationError) as caught:
        service.verify_and_parse(_body(), str(int(time.time())), "v0=invalid")
    assert getattr(caught.value, "status_code", None) == 503
    assert TEST_SLACK_SIGNING_SECRET not in str(caught.value)
