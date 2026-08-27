from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_risk_service
from app.schemas.risk import RiskDetailResponse, RiskListResponse
from app.services.risk_service import RiskService


router = APIRouter(
    prefix="/api/risks",
    tags=["Risks"]
)


@router.get(
    "",
    response_model=RiskListResponse,
    status_code=status.HTTP_200_OK
)
async def get_risks(
    industry_slug: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    service: RiskService = Depends(get_risk_service)
):
    try:
        risks = await service.get_all_risks(
            industry_slug=industry_slug,
            severity=severity,
            is_active=is_active
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch risks"
        )

    return {"success": True, "data": risks}


@router.get(
    "/{risk_id}",
    response_model=RiskDetailResponse,
    status_code=status.HTTP_200_OK
)
async def get_risk(
    risk_id: str,
    service: RiskService = Depends(get_risk_service)
):
    try:
        risk = await service.get_risk_by_id(risk_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk not found"
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch risk"
        )

    return {"success": True, "data": risk}
