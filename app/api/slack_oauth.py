import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import PyMongoError

from app.dependencies import (
    get_slack_oauth_service,
    get_slack_workspace_installation_service,
)
from app.exceptions import (
    SlackOAuthError,
)
from app.schemas.slack_workspace_installation import (
    SlackOAuthCallbackResponse,
)
from app.services.slack_oauth_service import SlackOAuthService
from app.services.slack_workspace_installation_service import (
    SlackWorkspaceInstallationService,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/slack/oauth",
    tags=["Slack OAuth"],
)


@router.get(
    "/callback",
    response_model=SlackOAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def slack_oauth_callback(
    code: str = Query(..., min_length=1),
    state: str | None = Query(default=None),
    oauth_service: SlackOAuthService = Depends(get_slack_oauth_service),
    installation_service: SlackWorkspaceInstallationService = Depends(
        get_slack_workspace_installation_service
    ),
):
    # `state` is accepted for the current MVP, but is intentionally not used
    # for client association until a signed/temporary state flow is available.
    del state

    try:
        installation = await oauth_service.exchange_code(code)
        saved, destination = (
            await installation_service.save_installation_and_destination(
                installation
            )
        )
    except SlackOAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
    except PyMongoError as exc:
        logger.exception("slack_oauth_installation_persist_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save Slack workspace installation",
        ) from exc
    except Exception as exc:
        # Do not include the exception text: unexpected errors must not make
        # it possible for a secret-bearing value to reach application logs.
        logger.error("slack_oauth_callback_failed error_code=unexpected_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete Slack workspace connection",
        ) from exc

    logger.info(
        "slack_channel_connected workspace_id=%s installation_id=%s destination_id=%s",
        saved["slack_team_id"],
        saved["_id"],
        destination["_id"] if destination else None,
    )

    return {
        "success": True,
        "message": (
            "Slack channel connected successfully"
            if destination
            else "Slack workspace connected successfully"
        ),
        "data": {
            "installation_id": str(saved["_id"]),
            "destination_id": (
                str(destination["_id"]) if destination else None
            ),
            "workspace_id": saved["slack_team_id"],
            "workspace_name": saved["slack_team_name"],
            "channel_id": destination.get("channel_id") if destination else None,
            "channel_name": destination.get("channel_name") if destination else None,
            "is_active": destination["is_active"] if destination else saved["is_active"],
        },
    }
