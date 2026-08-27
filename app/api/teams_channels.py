import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_database
from app.schemas.teams_channel import (
    TeamsChannelCreate,
    TeamsChannelCreateResponse,
    TeamsChannelGetResponse,
    TeamsChannelTestResponse,
    TeamsChannelUpdate,
    TeamsChannelUpdateResponse,
)
from app.dependencies import get_n8n_service
from app.exceptions import UpstreamError, UpstreamTimeoutError
from app.repositories.client_repository import ClientRepository
from app.repositories.teams_channel_repository import TeamsChannelRepository
from app.services.teams_channel_service import TeamsChannelService

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api",
    tags=["Teams Destinations"]
)


def _safe_channel_data(channel):
    return {
        "id": str(channel["_id"]),
        "client_id": str(channel["client_id"]),
        "team_name": channel["team_name"],
        "channel_name": channel.get("channel_name"),
        "channel_url": channel["channel_url"],
        "tenant_id": channel.get("tenant_id"),
        "team_id": channel.get("team_id"),
        "channel_id": channel.get("channel_id"),
        "webhook_configured": bool(channel.get("teams_webhook_url")),
        "is_active": channel["is_active"],
        "created_at": channel["created_at"],
        "updated_at": channel["updated_at"]
    }


def _dashboard_channel_data(channel):
    return {
        "id": str(channel["_id"]),
        "client_id": str(channel["client_id"]),
        "team_name": channel["team_name"],
        "team_id": channel.get("team_id"),
        "channel_name": channel.get("channel_name"),
        "channel_id": channel.get("channel_id"),
        "webhook_configured": bool(channel.get("teams_webhook_url")),
        "is_active": channel["is_active"],
        "created_at": channel["created_at"],
        "updated_at": channel["updated_at"]
    }


@router.put(
    "/teams/channels/{destination_id}",
    response_model=TeamsChannelUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_teams_channel(
    destination_id: str,
    payload: TeamsChannelUpdate,
    database=Depends(get_database),
):
    service = TeamsChannelService(
        teams_channel_repository=TeamsChannelRepository(database),
        client_repository=ClientRepository(database),
    )
    try:
        channel = await service.update_channel(destination_id, payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ValueError as exc:
        message = str(exc)
        response_status = (
            status.HTTP_409_CONFLICT
            if message in {
                "This Teams webhook is already configured",
                "This Teams channel is already configured",
            }
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=message)
    except Exception:
        logger.exception(
            "teams_destination_update_failed destination_id=%s",
            destination_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update Teams destination",
        )

    return {
        "success": True,
        "message": "Teams destination updated successfully",
        "data": _safe_channel_data(channel),
    }


@router.post(
    "/clients/{client_id}/teams/channels",
    response_model=TeamsChannelCreateResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_teams_channel(
    client_id: str,
    payload: TeamsChannelCreate,
    database=Depends(get_database)
):
    try:

        # Repositories
        client_repository = ClientRepository(database)

        teams_channel_repository = TeamsChannelRepository(
            database
        )

        # Service
        service = TeamsChannelService(
            teams_channel_repository=teams_channel_repository,
            client_repository=client_repository
        )

        # Create destination
        channel = await service.create_channel(
            client_id=client_id,
            team_name=payload.team_name,
            channel_url=str(payload.channel_url),
            teams_webhook_url=str(payload.teams_webhook_url)
        )

        # Safe response
        # IMPORTANT: webhook URL frontend ko return nahi karna.
        return {
            "success": True,
            "data": _safe_channel_data(channel)
        }

    except ValueError as exc:

        message = str(exc)

        if message == "Client not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message
            )

        if message in {
            "This Teams webhook is already configured",
            "This Teams channel is already configured"
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to configure Teams channel"
        )



@router.get(
    "/clients/{client_id}/teams/channels",
    status_code=status.HTTP_200_OK
)
async def get_client_teams_channels(
    client_id: str,
    dashboard_view: bool = Query(default=False, alias="dashboard"),
    database=Depends(get_database)
):
    try:

        client_repository = ClientRepository(database)

        teams_channel_repository = TeamsChannelRepository(
            database
        )

        service = TeamsChannelService(
            teams_channel_repository=teams_channel_repository,
            client_repository=client_repository
        )

        channels = await service.get_channels_by_client(
            client_id
        )

        return {
            "success": True,
            "data": [
                _dashboard_channel_data(channel)
                if dashboard_view
                else _safe_channel_data(channel)
                for channel in channels
            ]
        }

    except ValueError as exc:

        if str(exc) == "Client not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found"
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch Teams channels"
        )


@router.get(
    "/teams/channels/{destination_id}",
    response_model=TeamsChannelGetResponse,
    status_code=status.HTTP_200_OK
)
async def get_teams_channel(
    destination_id: str,
    database=Depends(get_database)
):
    service = TeamsChannelService(
        teams_channel_repository=TeamsChannelRepository(database),
        client_repository=ClientRepository(database)
    )

    try:
        channel = await service.get_channel_by_id(destination_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teams destination not found"
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch Teams destination"
        )

    return {
        "success": True,
        "data": _safe_channel_data(channel)
    }


@router.post(
    "/teams/channels/{destination_id}/test",
    response_model=TeamsChannelTestResponse,
    status_code=status.HTTP_200_OK
)
async def test_teams_channel(
    destination_id: str,
    database=Depends(get_database),
    n8n_service=Depends(get_n8n_service)
):
    service = TeamsChannelService(
        teams_channel_repository=TeamsChannelRepository(database),
        client_repository=ClientRepository(database),
        n8n_service=n8n_service
    )

    try:
        result = await service.test_channel(destination_id)
    except ValueError as exc:
        message = str(exc)
        response_status = (
            status.HTTP_404_NOT_FOUND
            if message == "Teams destination not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=message)
    except (UpstreamError, UpstreamTimeoutError) as exc:
        logger.error(
            "test_notification_failed destination_id=%s error_code=%s "
            "http_status=%s",
            destination_id,
            getattr(exc, "error_code", "n8n_timeout"),
            getattr(exc, "http_status", None),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send test notification"
        )
    except Exception:
        logger.error(
            "test_notification_failed destination_id=%s "
            "error_code=unexpected_error",
            destination_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to test Teams destination"
        )

    return {
        "success": True,
        "message": "Test notification sent successfully",
        "data": result
    }
