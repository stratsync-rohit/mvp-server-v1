import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_database
from app.dependencies import get_slack_n8n_service
from app.exceptions import UpstreamError, UpstreamTimeoutError
from app.repositories.client_repository import ClientRepository
from app.repositories.slack_destination_repository import SlackDestinationRepository
from app.schemas.slack_destination import (
    SlackDestinationCreate,
    SlackDestinationCreateResponse,
    SlackDestinationDeleteResponse,
    SlackDestinationGetResponse,
    SlackDestinationListResponse,
    SlackDestinationTestResponse,
    SlackDestinationUpdate,
    SlackDestinationUpdateResponse,
)
from app.services.slack_destination_service import SlackDestinationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Slack Destinations"])


def _safe_destination_data(destination):
    return {
        "id": str(destination["_id"]),
        "client_id": str(destination["client_id"]),
        "workspace_domain": destination["workspace_domain"],
        "channel_id": destination["channel_id"],
        "channel_name": destination["channel_name"],
        "channel_link": destination["channel_link"],
        "webhook_configured": bool(destination.get("webhook_url")),
        "is_active": destination["is_active"],
        "created_at": destination["created_at"],
        "updated_at": destination["updated_at"],
    }


def _service(database, slack_n8n_service=None):
    return SlackDestinationService(
        slack_destination_repository=SlackDestinationRepository(database),
        client_repository=ClientRepository(database),
        slack_n8n_service=slack_n8n_service,
    )


@router.post(
    "/clients/{client_id}/slack/channels",
    response_model=SlackDestinationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_slack_destination(
    client_id: str,
    payload: SlackDestinationCreate,
    database=Depends(get_database),
):
    try:
        destination = await _service(database).create_destination(
            client_id=client_id,
            channel_link=payload.channel_link,
            channel_name=payload.channel_name,
            webhook_url=payload.webhook_url,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        logger.error(
            "slack_destination_create_failed client_id=%s error_code=unexpected_error",
            client_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to configure Slack channel",
        )
    return {"success": True, "data": _safe_destination_data(destination)}


@router.get(
    "/clients/{client_id}/slack/channels",
    response_model=SlackDestinationListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_client_slack_destinations(
    client_id: str,
    database=Depends(get_database),
):
    try:
        destinations = await _service(database).get_destinations_by_client(client_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.error(
            "slack_destination_list_failed client_id=%s error_code=unexpected_error",
            client_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch Slack channels",
        )
    return {
        "success": True,
        "data": [_safe_destination_data(item) for item in destinations],
    }


@router.get(
    "/slack/channels/{destination_id}",
    response_model=SlackDestinationGetResponse,
    status_code=status.HTTP_200_OK,
)
async def get_slack_destination(
    destination_id: str,
    database=Depends(get_database),
):
    try:
        destination = await _service(database).get_destination_by_id(destination_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.error(
            "slack_destination_get_failed destination_id=%s error_code=unexpected_error",
            destination_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch Slack destination",
        )
    return {"success": True, "data": _safe_destination_data(destination)}


@router.put(
    "/slack/channels/{destination_id}",
    response_model=SlackDestinationUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_slack_destination(
    destination_id: str,
    payload: SlackDestinationUpdate,
    database=Depends(get_database),
):
    try:
        destination = await _service(database).update_destination(
            destination_id, payload
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        logger.error(
            "slack_destination_update_failed destination_id=%s "
            "error_code=unexpected_error",
            destination_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update Slack destination",
        )
    return {
        "success": True,
        "message": "Slack destination updated successfully",
        "data": _safe_destination_data(destination),
    }


@router.delete(
    "/slack/channels/{destination_id}",
    response_model=SlackDestinationDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_slack_destination(
    destination_id: str,
    database=Depends(get_database),
):
    try:
        destination = await _service(database).delete_destination(destination_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.error(
            "slack_destination_delete_failed destination_id=%s "
            "error_code=unexpected_error",
            destination_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete Slack destination",
        )
    return {
        "success": True,
        "message": "Slack destination disabled successfully",
        "data": _safe_destination_data(destination),
    }


@router.post(
    "/slack/channels/{destination_id}/test",
    response_model=SlackDestinationTestResponse,
    status_code=status.HTTP_200_OK,
)
async def test_slack_destination(
    destination_id: str,
    database=Depends(get_database),
    slack_n8n_service=Depends(get_slack_n8n_service),
):
    try:
        await _service(database, slack_n8n_service).test_destination(
            destination_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (UpstreamTimeoutError, UpstreamError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send Slack test notification",
        )
    except Exception:
        logger.error(
            "slack_destination_test_failed destination_id=%s "
            "error_code=unexpected_error",
            destination_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to test Slack destination",
        )
    return {
        "success": True,
        "status": "sent",
        "message": "Slack test notification sent successfully.",
    }
