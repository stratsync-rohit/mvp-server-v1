import logging
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
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


_HTML_STYLES = """
:root {
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  background: #f3f6fa;
  color: #172033;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: #f3f6fa;
}

.oauth-card {
  width: min(100%, 560px);
  padding: 44px 40px 36px;
  border: 1px solid #e3e8ef;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 18px 45px rgba(31, 45, 61, 0.09);
  text-align: center;
}

.oauth-icon {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  margin: 0 auto 24px;
  border-radius: 50%;
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
}

.oauth-icon.success {
  color: #16845a;
  background: #e8f7ef;
  box-shadow: inset 0 0 0 8px #f4fcf7;
}

.oauth-icon.error {
  color: #b42318;
  background: #fff0ee;
  box-shadow: inset 0 0 0 8px #fff8f7;
}

h1 {
  margin: 0;
  color: #172033;
  font-size: clamp(1.55rem, 4vw, 1.9rem);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

.oauth-message {
  max-width: 430px;
  margin: 14px auto 0;
  color: #5b6678;
  font-size: 1rem;
  line-height: 1.6;
}

.oauth-details {
  display: grid;
  gap: 10px;
  margin: 28px 0 0;
  text-align: left;
}

.oauth-detail-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 13px 16px;
  border: 1px solid #e7ebf0;
  border-radius: 12px;
  background: #f8fafc;
}

.oauth-detail-label {
  color: #6a7586;
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.oauth-detail-value {
  min-width: 0;
  color: #263247;
  font-size: 0.95rem;
  font-weight: 600;
  overflow-wrap: anywhere;
  text-align: right;
}

.oauth-hint {
  margin: 28px 0 0;
  color: #8993a2;
  font-size: 0.88rem;
  line-height: 1.5;
}

@media (max-width: 480px) {
  .oauth-card {
    padding: 34px 22px 28px;
    border-radius: 16px;
  }

  .oauth-detail-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }

  .oauth-detail-value {
    text-align: left;
  }
}
"""


def _html_page(
    *,
    title: str,
    message: str,
    status_code: int,
    variant: str,
    hint: str,
    details_html: str = "",
) -> HTMLResponse:
    icon = "✓" if variant == "success" else "!"
    return HTMLResponse(
        content=(
            "<!doctype html>"
            "<html lang=\"en\"><head>"
            "<meta charset=\"utf-8\">"
            "<meta name=\"viewport\" "
            "content=\"width=device-width, initial-scale=1\">"
            f"<title>{escape(title)}</title>"
            f"<style>{_HTML_STYLES}</style>"
            "</head><body>"
            "<main class=\"oauth-card\">"
            f"<div class=\"oauth-icon {escape(variant)}\" "
            f"aria-hidden=\"true\">{icon}</div>"
            f"<h1>{escape(title)}</h1>"
            f"<p class=\"oauth-message\">{escape(message)}</p>"
            f"{details_html}"
            f"<p class=\"oauth-hint\">{escape(hint)}</p>"
            "</main></body></html>"
        ),
        status_code=status_code,
    )


def _oauth_error_response(
    reason: str,
    response_status: int | None = None,
) -> HTMLResponse:
    pages = {
        "workspace_conflict": (
            "Slack Connection Failed",
            "This Slack workspace is already connected to another "
            "StratSync client. Please contact your StratSync administrator.",
            status.HTTP_409_CONFLICT,
        ),
        "oauth_denied": (
            "Slack Connection Cancelled",
            "Slack authorization was not completed.",
            status.HTTP_400_BAD_REQUEST,
        ),
        "invalid_state": (
            "Slack Connection Failed",
            "This connection link is invalid or has expired. Please request "
            "a new Slack Connect URL.",
            status.HTTP_400_BAD_REQUEST,
        ),
        "oauth_exchange_failed": (
            "Slack Connection Failed",
            "We could not complete the Slack connection. Please try again "
            "or contact support.",
            status.HTTP_502_BAD_GATEWAY,
        ),
        "configuration_error": (
            "Slack Connection Failed",
            "We could not complete the Slack connection. Please try again "
            "or contact support.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
        "unknown_error": (
            "Slack Connection Failed",
            "We could not complete the Slack connection. Please try again "
            "or contact support.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
    }
    title, message, status_code = pages.get(
        reason,
        pages["unknown_error"],
    )
    return _html_page(
        title=title,
        message=message,
        status_code=response_status or status_code,
        variant="error",
        hint="You can close this window and try again when ready.",
    )


def _oauth_success_response(
    saved: dict,
    destination: dict | None,
) -> HTMLResponse:
    details = []
    workspace_name = saved.get("slack_team_name")
    if isinstance(workspace_name, str) and workspace_name:
        details.append(
            "<div class=\"oauth-detail-row\">"
            "<span class=\"oauth-detail-label\">Workspace</span>"
            f"<span class=\"oauth-detail-value\">"
            f"{escape(workspace_name)}</span></div>"
        )

    channel_name = destination.get("channel_name") if destination else None
    if isinstance(channel_name, str) and channel_name:
        details.append(
            "<div class=\"oauth-detail-row\">"
            "<span class=\"oauth-detail-label\">Channel</span>"
            f"<span class=\"oauth-detail-value\">"
            f"{escape(channel_name)}</span></div>"
        )

    return _html_page(
        title="Slack Connected Successfully",
        message="Your Slack workspace and channel are now connected to "
        "StratSync.",
        status_code=status.HTTP_200_OK,
        variant="success",
        hint="You can now close this window.",
        details_html=(
            f"<section class=\"oauth-details\" "
            f"aria-label=\"Connection details\">{''.join(details)}</section>"
            if details
            else ""
        ),
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
    status_code=status.HTTP_200_OK,
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
):
    if error:
        logger.info("slack_oauth_callback_denied")
        return _oauth_error_response("oauth_denied")

    if not state:
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_response("invalid_state")

    if not code:
        logger.warning(
            "slack_oauth_callback_failed error_code=oauth_exchange_failed"
        )
        return _oauth_error_response("oauth_exchange_failed")

    try:
        client_id = await state_service.validate_state(state)
    except SlackOAuthStateError:
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_response("invalid_state")
    except SlackOAuthStateConfigurationError as exc:
        logger.error(
            "slack_oauth_callback_failed error_code=configuration_error"
        )
        return _oauth_error_response(
            "configuration_error",
            response_status=exc.status_code,
        )
    except (LookupError, ValueError):
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_response("invalid_state")
    except Exception:
        logger.error("slack_oauth_callback_failed error_code=unknown_error")
        return _oauth_error_response("unknown_error")

    try:
        installation = await oauth_service.exchange_code(code)
    except SlackOAuthConfigurationError as exc:
        logger.error(
            "slack_oauth_callback_failed error_code=configuration_error"
        )
        return _oauth_error_response(
            "configuration_error",
            response_status=exc.status_code,
        )
    except SlackOAuthError as exc:
        logger.error(
            "slack_oauth_callback_failed error_code=oauth_exchange_failed"
        )
        return _oauth_error_response(
            "oauth_exchange_failed",
            response_status=exc.status_code,
        )
    except Exception:
        logger.error(
            "slack_oauth_callback_failed error_code=oauth_exchange_failed"
        )
        return _oauth_error_response("oauth_exchange_failed")

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
        return _oauth_error_response("workspace_conflict")
    except FileExistsError:
        logger.warning(
            "slack_oauth_callback_failed error_code=workspace_conflict"
        )
        return _oauth_error_response("workspace_conflict")
    except SlackOAuthStateError:
        logger.warning("slack_oauth_callback_failed error_code=invalid_state")
        return _oauth_error_response("invalid_state")
    except SlackOAuthStateConfigurationError as exc:
        logger.error(
            "slack_oauth_callback_failed error_code=configuration_error"
        )
        return _oauth_error_response(
            "configuration_error",
            response_status=exc.status_code,
        )
    except PyMongoError:
        logger.exception("slack_oauth_installation_persist_failed")
        return _oauth_error_response("unknown_error")
    except Exception:
        # Do not include the exception text: unexpected errors must not make
        # it possible for a secret-bearing value to reach application logs.
        logger.error("slack_oauth_callback_failed error_code=unexpected_error")
        return _oauth_error_response("unknown_error")

    logger.info(
        "slack_channel_connected workspace_id=%s installation_id=%s destination_id=%s",
        saved["slack_team_id"],
        saved["_id"],
        destination["_id"] if destination else None,
    )

    return _oauth_success_response(saved, destination)
