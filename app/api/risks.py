from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_risk_service
from app.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.schemas.risk import (
    RiskCreate,
    RiskCreateResponse,
    RiskDeleteResponse,
    RiskDetailResponse,
    RiskListResponse,
    RiskUpdateResponse,
)
from app.services.risk_service import RiskService


router = APIRouter(
    prefix="/api/risks",
    tags=["Risks"]
)


@router.post(
    "",
    response_model=RiskCreateResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_risk(
    payload: RiskCreate,
    service: RiskService = Depends(get_risk_service),
):
    try:
        risk = await service.create_risk(payload)
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create risk",
        ) from exc

    return {
        "message": "Risk created successfully",
        "risk_id": risk["risk_id"],
        "_id": str(risk["_id"]),
    }


@router.put(
    "/{risk_id}",
    response_model=RiskUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_risk(
    risk_id: str,
    payload: RiskCreate,
    service: RiskService = Depends(get_risk_service),
):
    try:
        await service.update_risk(risk_id, payload)
    except ValidationAppError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update risk",
        ) from exc

    return {"message": "Risk updated successfully", "risk_id": risk_id}


@router.delete(
    "/{risk_id}",
    response_model=RiskDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_risk(
    risk_id: str,
    service: RiskService = Depends(get_risk_service),
):
    try:
        await service.delete_risk(risk_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete risk",
        ) from exc

    return {"message": "Risk deleted successfully", "risk_id": risk_id}


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
