from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_industry_service, get_risk_service
from app.schemas.industry import IndustryListResponse, IndustryRiskListResponse
from app.services.industry_service import IndustryService
from app.services.risk_service import RiskService


router = APIRouter(
    prefix="/api/industries",
    tags=["Industries"]
)


@router.get(
    "",
    response_model=IndustryListResponse,
    status_code=status.HTTP_200_OK
)
async def get_industries(
    service: IndustryService = Depends(get_industry_service)
):
    try:
        industries = await service.get_industries()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch industries"
        )

    return {"success": True, "data": industries}


@router.get(
    "/{industry_slug}/risks",
    response_model=IndustryRiskListResponse,
    status_code=status.HTTP_200_OK
)
async def get_industry_risks(
    industry_slug: str,
    service: RiskService = Depends(get_risk_service)
):
    try:
        risks = await service.get_risks_by_industry(industry_slug)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Industry not found"
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch industry risks"
        )

    return {"success": True, "data": risks}
