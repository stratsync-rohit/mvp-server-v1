import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

from app.exceptions import (
    SlackInteractionConfigurationError,
    SlackInteractionValidationError,
    SlackSignatureVerificationError,
)
from app.schemas.slack_interaction import SlackNormalizedInteraction


SUPPORTED_ACTIONS = {"view_details", "mitigation_plan"}
MAX_REQUEST_AGE_SECONDS = 300


class SlackInteractionService:
    def __init__(self, settings):
        signing_secret = settings.slack_signing_secret
        self._signing_secret = signing_secret.strip() if signing_secret else None

    def verify_and_parse(
        self,
        raw_body: bytes,
        request_timestamp: str | None,
        request_signature: str | None,
    ) -> SlackNormalizedInteraction:
        self._verify_signature(raw_body, request_timestamp, request_signature)
        return self._parse_interaction(raw_body)

    def _verify_signature(
        self,
        raw_body: bytes,
        request_timestamp: str | None,
        request_signature: str | None,
    ) -> None:
        if not self._signing_secret:
            raise SlackInteractionConfigurationError(
                "Slack interactions are not configured"
            )
        if not request_timestamp or not request_signature:
            raise SlackSignatureVerificationError(
                "Invalid Slack request signature"
            )

        try:
            timestamp = int(request_timestamp)
        except (TypeError, ValueError):
            raise SlackSignatureVerificationError(
                "Invalid Slack request signature"
            )

        if abs(time.time() - timestamp) > MAX_REQUEST_AGE_SECONDS:
            raise SlackSignatureVerificationError(
                "Invalid Slack request signature"
            )

        signature_base = (
            b"v0:" + request_timestamp.encode("utf-8") + b":" + raw_body
        )
        expected_signature = "v0=" + hmac.new(
            self._signing_secret.encode("utf-8"),
            signature_base,
            hashlib.sha256,
        ).hexdigest()
        try:
            signature_matches = hmac.compare_digest(
                expected_signature, request_signature
            )
        except TypeError:
            signature_matches = False
        if not signature_matches:
            raise SlackSignatureVerificationError(
                "Invalid Slack request signature"
            )

    @staticmethod
    def _parse_interaction(raw_body: bytes) -> SlackNormalizedInteraction:
        try:
            form_data = parse_qs(
                raw_body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
            )
            payload_values = form_data.get("payload")
            if not payload_values or len(payload_values) != 1:
                raise ValueError
            payload = json.loads(payload_values[0])
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            raise SlackInteractionValidationError(
                "Invalid Slack interaction payload"
            )

        if not isinstance(payload, dict) or payload.get("type") != "block_actions":
            raise SlackInteractionValidationError(
                "Invalid Slack interaction payload"
            )

        actions = payload.get("actions")
        action = actions[0] if isinstance(actions, list) and actions else None
        if not isinstance(action, dict):
            raise SlackInteractionValidationError(
                "Invalid Slack interaction payload"
            )

        action_id = action.get("action_id")
        if not isinstance(action_id, str) or action_id not in SUPPORTED_ACTIONS:
            raise SlackInteractionValidationError(
                "Unsupported Slack interaction action"
            )

        try:
            button_value = json.loads(action.get("value", ""))
        except (TypeError, json.JSONDecodeError):
            raise SlackInteractionValidationError(
                "Invalid Slack interaction payload"
            )
        if not isinstance(button_value, dict):
            raise SlackInteractionValidationError(
                "Invalid Slack interaction payload"
            )

        risk_id = button_value.get("riskId")
        action_key = button_value.get("actionKey")
        response_url = payload.get("response_url")
        user = payload.get("user")
        channel = payload.get("channel")
        user_id = user.get("id") if isinstance(user, dict) else None
        channel_id = channel.get("id") if isinstance(channel, dict) else None
        channel_name = channel.get("name") if isinstance(channel, dict) else None

        required_strings = (risk_id, action_key, response_url, user_id, channel_id)
        if any(
            not isinstance(value, str) or not value.strip()
            for value in required_strings
        ):
            raise SlackInteractionValidationError(
                "Invalid Slack interaction payload"
            )
        if action_key not in SUPPORTED_ACTIONS or action_key != action_id:
            raise SlackInteractionValidationError(
                "Unsupported Slack interaction action"
            )
        if not isinstance(channel_name, str) or not channel_name.strip():
            channel_name = None

        return SlackNormalizedInteraction(
            riskId=risk_id.strip(),
            actionKey=action_key,
            actionId=action_id,
            responseUrl=response_url.strip(),
            userId=user_id.strip(),
            channelId=channel_id.strip(),
            channelName=channel_name.strip() if channel_name else None,
        )
