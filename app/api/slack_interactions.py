import json
import logging

import httpx

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

from app.config import Settings, get_settings
from app.dependencies import get_risk_service
from app.services.risk_service import RiskService
from app.services.slack_block_renderer import (
    build_slack_notification_payload,
    build_slack_risk_view_payload,
)
from app.services.slack_signature_service import verify_slack_signature


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/slack",
    tags=["Slack Interactions"],
)


# =========================================================
# HELPERS
# =========================================================

def _parse_action_value(raw_value: str) -> dict:
    try:
        value = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack action value",
        ) from exc

    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack action value",
        )

    return value


def _resolve_view(
    action_id: str,
    action_value: dict,
) -> str:
    """
    Resolve the requested risk view.

    New generic buttons send:
        {
            "risk_id": "...",
            "view": "details"
        }

    Legacy action IDs are also supported temporarily.
    """

    view = action_value.get("view")

    if isinstance(view, str):
        view = view.strip().lower()

    legacy_action_map = {
        "view_details": "details",
        "risk_view_details": "details",
        "mitigation_plan": "mitigation",
        "risk_view_mitigation": "mitigation",
        "risk_view_notification": "notification",
    }

    if not view:
        view = legacy_action_map.get(action_id)

    supported_views = {
        "notification",
        "details",
        "mitigation",
    }

    if view not in supported_views:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported Slack interaction view",
        )

    return view


async def _send_slack_response(
    response_url: str,
    slack_payload: dict,
) -> None:
    """
    Send the rendered view back through Slack's response_url.

    response_type=ephemeral:
        Only the user who clicked the button sees the response.

    replace_original=False:
        Original risk alert remains unchanged.
    """

    response_body = {
        "response_type": "ephemeral",
        "replace_original": False,
        "text": slack_payload.get(
            "text",
            "Risk details",
        ),
        "blocks": slack_payload.get(
            "blocks",
            [],
        ),
    }

    try:
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.post(
                response_url,
                json=response_body,
            )

            response.raise_for_status()

    except httpx.TimeoutException as exc:
        logger.error(
            "slack_interaction_response_failed "
            "error_code=slack_timeout"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack response timed out",
        ) from exc

    except httpx.HTTPStatusError as exc:
        logger.error(
            "slack_interaction_response_failed "
            "error_code=slack_http_error "
            "http_status=%s",
            exc.response.status_code,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack rejected interaction response",
        ) from exc

    except httpx.RequestError as exc:
        logger.error(
            "slack_interaction_response_failed "
            "error_code=slack_connection_error"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to connect to Slack",
        ) from exc


# =========================================================
# SLACK INTERACTIVITY ENDPOINT
#
# Slack App:
# Interactivity & Shortcuts
#
# Request URL:
# https://<backend>/api/slack/interactions
# =========================================================

@router.post(
    "/interactions",
    status_code=status.HTTP_200_OK,
)
async def slack_interactions(
    request: Request,
    service: RiskService = Depends(get_risk_service),
    settings: Settings = Depends(get_settings),
):
    raw_body = await request.body()

    if not settings.slack_signing_secret:
        logger.error("slack_signature_verification_not_configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack request verification is not configured",
        )

    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not verify_slack_signature(
        raw_body=raw_body,
        timestamp=timestamp,
        signature=signature,
        signing_secret=settings.slack_signing_secret,
    ):
        logger.warning("slack_signature_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )

    logger.info("slack_signature_verified")

    form = await request.form()
    payload = form.get("payload")
    if not isinstance(payload, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack interaction payload",
        )

    # -----------------------------------------------------
    # Parse Slack form-urlencoded payload
    # -----------------------------------------------------

    try:
        interaction = json.loads(payload)

    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack interaction payload",
        ) from exc

    if not isinstance(interaction, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack interaction payload",
        )

    # -----------------------------------------------------
    # Currently handle Block Kit button actions
    # -----------------------------------------------------

    interaction_type = interaction.get("type")

    if interaction_type != "block_actions":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported Slack interaction type: "
                f"{interaction_type}"
            ),
        )

    # -----------------------------------------------------
    # Extract action
    # -----------------------------------------------------

    actions = interaction.get("actions") or []

    if not actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack interaction contains no action",
        )

    action = actions[0]

    action_id = str(
        action.get("action_id") or ""
    ).strip()

    raw_action_value = action.get("value")

    if not raw_action_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack action value is missing",
        )

    action_value = _parse_action_value(
        raw_action_value
    )

    # -----------------------------------------------------
    # Resolve Risk ID
    # -----------------------------------------------------

    risk_id = (
        action_value.get("risk_id")
        or action_value.get("riskId")
    )

    if not risk_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Risk ID is missing from Slack action",
        )

    risk_id = str(risk_id).strip()

    # -----------------------------------------------------
    # Resolve requested view
    # -----------------------------------------------------

    view = _resolve_view(
        action_id=action_id,
        action_value=action_value,
    )

    # -----------------------------------------------------
    # Slack response URL
    # -----------------------------------------------------

    response_url = interaction.get(
        "response_url"
    )

    if not response_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack response_url is missing",
        )

    # -----------------------------------------------------
    # Load Risk V2
    # -----------------------------------------------------

    try:
        risk = await service.get_risk_by_id(
            risk_id
        )

    except Exception as exc:
        logger.exception(
            "slack_interaction_risk_fetch_failed "
            "risk_id=%s",
            risk_id,
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk not found",
        ) from exc

    if not risk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk not found",
        )

    # -----------------------------------------------------
    # Render requested Slack view
    # -----------------------------------------------------

    try:
        if view == "notification":
            slack_payload = (
                build_slack_notification_payload(
                    risk
                )
            )

        else:
            slack_payload = (
                build_slack_risk_view_payload(
                    risk,
                    view,
                )
            )

    except Exception as exc:
        logger.exception(
            "slack_interaction_render_failed "
            "risk_id=%s view=%s",
            risk_id,
            view,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to render Slack risk view",
        ) from exc

    # -----------------------------------------------------
    # Send rendered view directly to Slack
    # -----------------------------------------------------

    await _send_slack_response(
        response_url=response_url,
        slack_payload=slack_payload,
    )

    logger.info(
        "slack_interaction_completed "
        "risk_id=%s view=%s action_id=%s",
        risk_id,
        view,
        action_id,
    )

    # Slack expects quick HTTP 200 acknowledgement.
    return {
        "ok": True,
        "risk_id": risk_id,
        "view": view,
    }
