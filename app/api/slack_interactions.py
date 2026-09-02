import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)

from app.dependencies import (
    get_slack_interaction_n8n_service,
    get_slack_interaction_service,
)
from app.exceptions import AppError, UpstreamError, UpstreamTimeoutError
from app.services.n8n_service import N8nService
from app.services.slack_interaction_service import SlackInteractionService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slack", tags=["Slack Interactions"])


async def forward_slack_interaction(
    n8n_service: N8nService, normalized_payload: dict
) -> None:
    try:
        await n8n_service.trigger_notification(normalized_payload)
    except UpstreamTimeoutError:
        logger.error(
            "slack_interaction_forward_failed error_code=n8n_timeout"
        )
    except UpstreamError as exc:
        logger.error(
            "slack_interaction_forward_failed error_code=%s",
            exc.error_code,
        )
    except Exception:
        logger.error(
            "slack_interaction_forward_failed error_code=unexpected_error"
        )


@router.post("/interactions", status_code=200, response_class=Response)
async def receive_slack_interaction(
    request: Request,
    background_tasks: BackgroundTasks,
    interaction_service: SlackInteractionService = Depends(
        get_slack_interaction_service
    ),
    n8n_service: N8nService = Depends(get_slack_interaction_n8n_service),
) -> Response:
    raw_body = await request.body()
    try:
        normalized = interaction_service.verify_and_parse(
            raw_body=raw_body,
            request_timestamp=request.headers.get("X-Slack-Request-Timestamp"),
            request_signature=request.headers.get("X-Slack-Signature"),
        )
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    background_tasks.add_task(
        forward_slack_interaction,
        n8n_service,
        normalized.model_dump(by_alias=True),
    )
    return Response(status_code=200)
