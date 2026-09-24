import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pymongo.errors import PyMongoError

from app.dependencies import (
    get_slack_connection_token_service,
    get_slack_oauth_service,
    get_slack_oauth_state_service,
    get_slack_workspace_installation_service,
)
from app.exceptions import (
    ConflictError,
    SlackConnectionTokenError,
    SlackOAuthError,
)
from app.schemas.slack_workspace_installation import (
    SlackOAuthCallbackResponse,
)
from app.services.slack_oauth_service import SlackOAuthService
from app.services.slack_connection_token_service import SlackConnectionTokenService
from app.services.slack_oauth_state_service import SlackOAuthStateService
from app.services.slack_workspace_installation_service import (
    SlackWorkspaceInstallationService,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/slack/oauth",
    tags=["Slack OAuth"],
)


@router.get(
    "/start",
    status_code=status.HTTP_302_FOUND,
)
async def slack_oauth_start(
    token: str = Query(..., min_length=1),
    token_service: SlackConnectionTokenService = Depends(
        get_slack_connection_token_service
    ),
    oauth_service: SlackOAuthService = Depends(get_slack_oauth_service),
    state_service: SlackOAuthStateService = Depends(
        get_slack_oauth_state_service
    ),
):
    try:
        connection = await token_service.resolve(token)
        client_id = str(connection["client_id"])
        state = await state_service.create_state(
            client_id,
            connection_token_id=connection["_id"],
        )
        authorization_url = oauth_service.build_authorization_url(state)
    except SlackConnectionTokenError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
    except SlackOAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Slack connection token not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PyMongoError as exc:
        logger.exception("slack_oauth_start_client_lookup_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to start Slack workspace connection",
        ) from exc

    return RedirectResponse(
        url=authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/callback",
    response_model=SlackOAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def slack_oauth_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    oauth_service: SlackOAuthService = Depends(get_slack_oauth_service),
    state_service: SlackOAuthStateService = Depends(
        get_slack_oauth_state_service
    ),
    installation_service: SlackWorkspaceInstallationService = Depends(
        get_slack_workspace_installation_service
    ),
):
    try:
        client_id = await state_service.validate_state(state)
        installation = await oauth_service.exchange_code(code)
        saved, destination = (
            await installation_service.save_installation_and_destination(
                installation,
                client_id=client_id,
            )
        )
        await state_service.mark_used(state)
    except SlackOAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
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
