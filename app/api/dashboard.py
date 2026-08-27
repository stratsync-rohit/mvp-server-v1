from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_dashboard_service
from app.schemas.dashboard import DashboardSummaryResponse, RecentIntegrationsResponse
from app.services.dashboard_service import DashboardService


router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"]
)


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK
)
async def get_dashboard_summary(
    client_id: str | None = Query(default=None),
    service: DashboardService = Depends(get_dashboard_service)
):
    try:
        summary = await service.get_summary(client_id=client_id)
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
            detail="Unable to fetch dashboard summary"
        )

    return {"success": True, "data": summary}


@router.get(
    "/recent-integrations",
    response_model=RecentIntegrationsResponse,
    status_code=status.HTTP_200_OK
)
async def get_recent_integrations(
    limit: int = Query(default=5, ge=1, le=20),
    service: DashboardService = Depends(get_dashboard_service)
):
    try:
        integrations = await service.get_recent_integrations(limit=limit)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch recent Teams integrations"
        )

    return {"success": True, "data": integrations}
