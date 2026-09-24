import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
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
    SlackOAuthConfigurationError,
    SlackOAuthStateConfigurationError,
    SlackOAuthStateError,
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


def _oauth_error_redirect(
    settings: Settings,
    reason: str,
) -> RedirectResponse:
    separator = "&" if "?" in settings.slack_oauth_error_url else "?"
    return RedirectResponse(
        url=(
            f"{settings.slack_oauth_error_url}"
            f"{separator}{urlencode({'reason': reason})}"
        ),
        status_code=status.HTTP_303_SEE_OTHER,
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
    status_code=status.HTTP_303_SEE_OTHER,
)
async def slack_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    oauth_service: SlackOAuthService = Depends(get_slack_oauth_service),
    state_service: SlackOAuthStateService = Depends(
        get_slack_oauth_state_service
    ),
    installation_service: SlackWorkspaceInstallationService = Depends(
        get_slack_workspace_installation_service
    ),
    settings: Settings = Depends(get_settings),
):
    if error:
        logger.info("slack_oauth_callback_denied")
        return _oauth_error_redirect(settings, "oauth_denied")

    if not state:
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_redirect(settings, "invalid_state")

    if not code:
        logger.warning(
            "slack_oauth_callback_failed error_code=oauth_exchange_failed"
        )
        return _oauth_error_redirect(settings, "oauth_exchange_failed")

    try:
        client_id = await state_service.validate_state(state)
    except SlackOAuthStateError:
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_redirect(settings, "invalid_state")
    except SlackOAuthStateConfigurationError:
        logger.error(
            "slack_oauth_callback_failed error_code=configuration_error"
        )
        return _oauth_error_redirect(settings, "configuration_error")
    except (LookupError, ValueError):
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_redirect(settings, "invalid_state")
    except Exception:
        logger.error("slack_oauth_callback_failed error_code=unknown_error")
        return _oauth_error_redirect(settings, "unknown_error")

    try:
        installation = await oauth_service.exchange_code(code)
    except SlackOAuthConfigurationError:
        logger.error(
            "slack_oauth_callback_failed error_code=configuration_error"
        )
        return _oauth_error_redirect(settings, "configuration_error")
    except SlackOAuthError:
        logger.error(
            "slack_oauth_callback_failed error_code=oauth_exchange_failed"
        )
        return _oauth_error_redirect(settings, "oauth_exchange_failed")
    except Exception:
        logger.error(
            "slack_oauth_callback_failed error_code=oauth_exchange_failed"
        )
        return _oauth_error_redirect(settings, "oauth_exchange_failed")

    try:
        saved, destination = (
            await installation_service.save_installation_and_destination(
                installation,
                client_id=client_id,
            )
        )
        await state_service.mark_used(state)
    except ConflictError:
        logger.warning(
            "slack_oauth_callback_failed error_code=workspace_conflict"
        )
        return _oauth_error_redirect(settings, "workspace_conflict")
    except FileExistsError:
        logger.warning(
            "slack_oauth_callback_failed error_code=workspace_conflict"
        )
        return _oauth_error_redirect(settings, "workspace_conflict")
    except SlackOAuthStateError:
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_redirect(settings, "invalid_state")
    except SlackOAuthStateConfigurationError:
        logger.error(
            "slack_oauth_callback_failed error_code=configuration_error"
        )
        return _oauth_error_redirect(settings, "configuration_error")
    except PyMongoError:
        logger.exception("slack_oauth_installation_persist_failed")
        return _oauth_error_redirect(settings, "unknown_error")
    except Exception:
        # Do not include the exception text: unexpected errors must not make
        # it possible for a secret-bearing value to reach application logs.
        logger.error("slack_oauth_callback_failed error_code=unexpected_error")
        return _oauth_error_redirect(settings, "unknown_error")

    logger.info(
        "slack_channel_connected workspace_id=%s installation_id=%s destination_id=%s",
        saved["slack_team_id"],
        saved["_id"],
        destination["_id"] if destination else None,
    )

    return RedirectResponse(
        url=settings.slack_oauth_success_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
