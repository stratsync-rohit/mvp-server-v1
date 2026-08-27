from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_notification_service
from app.exceptions import AppError, UpstreamError, UpstreamTimeoutError
from app.schemas.notification import (
    NotificationHistoryResponse,
    NotificationTriggerRequest,
    NotificationTriggerResponse
)
from app.services.notification_service import NotificationService


router = APIRouter(
    prefix="/api/notifications",
    tags=["Notifications"]
)


@router.post(
    "/trigger",
    response_model=NotificationTriggerResponse,
    status_code=status.HTTP_200_OK
)
async def trigger_notification(
    payload: NotificationTriggerRequest,
    service: NotificationService = Depends(get_notification_service)
):
    try:
        result = await service.trigger_notification(
            risk_id=payload.risk_id,
            destination_id=payload.destination_id
        )
    except (UpstreamTimeoutError, UpstreamError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send notification"
        )
    except AppError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process notification"
        )

    return {
        "success": True,
        "message": "Notification sent successfully",
        "data": result
    }


@router.get(
    "",
    response_model=NotificationHistoryResponse,
    status_code=status.HTTP_200_OK
)
async def get_notifications(
    client_id: str | None = Query(default=None),
    risk_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    destination_id: str | None = Query(default=None),
    service: NotificationService = Depends(get_notification_service)
):
    try:
        notifications = await service.get_notifications(
            client_id=client_id,
            risk_id=risk_id,
            status=status_filter,
            destination_id=destination_id
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch notifications"
        )

    return {"success": True, "data": notifications}
