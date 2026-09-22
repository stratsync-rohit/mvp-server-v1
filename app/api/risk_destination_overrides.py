from copy import deepcopy

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.dependencies import (
    get_risk_destination_override_service,
    get_risk_service,
)

from app.exceptions import NotFoundError

from app.schemas.risk_destination_override import (
    RiskDestinationOverrideUpsert,
)

from app.services.risk_destination_override_service import (
    RiskDestinationOverrideService,
)

from app.services.risk_service import RiskService


router = APIRouter(
    prefix="/api/risks",
    tags=["Risk Destination Overrides"],
)


# =========================================================
# CREATE / UPDATE DESTINATION OVERRIDE
# =========================================================

@router.put(
    "/{risk_id}/destinations/{destination_id}/override",
    status_code=status.HTTP_200_OK,
)
async def upsert_risk_destination_override(
    risk_id: str,
    destination_id: str,
    payload: RiskDestinationOverrideUpsert,
    override_service: RiskDestinationOverrideService = Depends(
        get_risk_destination_override_service
    ),
    risk_service: RiskService = Depends(
        get_risk_service
    ),
):
    try:
        # Make sure the base risk actually exists.
        risk = await risk_service.get_risk_by_id(
            risk_id
        )

        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk not found",
            )

        # Service layer handles repository interaction.
        override = await override_service.upsert_override(
            risk_id=risk_id,
            destination_id=destination_id,
            overrides=payload.overrides,
            is_active=payload.is_active,
        )

        return {
            "success": True,
            "message": "Risk destination override saved successfully",
            "data": {
                "id": str(override["_id"]),
                "risk_id": override["risk_id"],
                "destination_id": override["destination_id"],
                "overrides": override.get(
                    "overrides",
                    {},
                ),
                "is_active": override.get(
                    "is_active",
                    True,
                ),
                "created_at": override.get(
                    "created_at"
                ),
                "updated_at": override.get(
                    "updated_at"
                ),
            },
        }

    except HTTPException:
        raise

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save risk destination override",
        ) from exc


# =========================================================
# GET DESTINATION OVERRIDE
# =========================================================

@router.get(
    "/{risk_id}/destinations/{destination_id}/override",
    status_code=status.HTTP_200_OK,
)
async def get_risk_destination_override(
    risk_id: str,
    destination_id: str,
    service: RiskDestinationOverrideService = Depends(
        get_risk_destination_override_service
    ),
):
    try:
        override = await service.get_override(
            risk_id=risk_id,
            destination_id=destination_id,
        )

        if not override:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk destination override not found",
            )

        return {
            "success": True,
            "data": {
                "id": str(override["_id"]),
                "risk_id": override["risk_id"],
                "destination_id": override["destination_id"],
                "overrides": override.get(
                    "overrides",
                    {},
                ),
                "is_active": override.get(
                    "is_active",
                    True,
                ),
                "created_at": override.get(
                    "created_at"
                ),
                "updated_at": override.get(
                    "updated_at"
                ),
            },
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch risk destination override",
        ) from exc


# =========================================================
# GET RESOLVED RISK PREVIEW
# =========================================================

@router.get(
    "/{risk_id}/destinations/{destination_id}/resolved",
    status_code=status.HTTP_200_OK,
)
async def get_resolved_risk_preview(
    risk_id: str,
    destination_id: str,
    override_service: RiskDestinationOverrideService = Depends(
        get_risk_destination_override_service
    ),
    risk_service: RiskService = Depends(
        get_risk_service
    ),
):
    """
    Return the final resolved risk for a destination.

    Base Risk + Active Destination Override = Resolved Risk.

    This endpoint is read-only and does not send a notification.
    """

    try:
        # Load base risk.
        base_risk = await risk_service.get_risk_by_id(
            risk_id
        )

        if not base_risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk not found",
            )

        # Check whether an active override exists.
        override = await override_service.get_override(
            risk_id=risk_id,
            destination_id=destination_id,
        )

        has_override = override is not None

        # Resolve base risk + destination override.
        resolved_risk = await override_service.resolve_risk(
            risk=base_risk,
            destination_id=destination_id,
        )

        # Make response JSON-safe without mutating the source object.
        resolved_risk = deepcopy(
            resolved_risk
        )

        if resolved_risk.get("_id") is not None:
            resolved_risk["_id"] = str(
                resolved_risk["_id"]
            )

        return {
            "success": True,
            "data": {
                "risk_id": risk_id,
                "destination_id": destination_id,
                "has_override": has_override,
                "risk": resolved_risk,
            },
        }

    except HTTPException:
        raise

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve risk destination preview",
        ) from exc


# =========================================================
# LIST DESTINATION OVERRIDES FOR RISK
# =========================================================

@router.get(
    "/{risk_id}/destination-overrides",
    status_code=status.HTTP_200_OK,
)
async def list_risk_destination_overrides(
    risk_id: str,
    override_service: RiskDestinationOverrideService = Depends(
        get_risk_destination_override_service
    ),
    risk_service: RiskService = Depends(
        get_risk_service
    ),
):
    """
    Return all active destination overrides configured
    for the given risk.
    """

    try:
        # Make sure the base risk exists.
        risk = await risk_service.get_risk_by_id(
            risk_id
        )

        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk not found",
            )

        # Fetch active overrides for this risk.
        overrides = await override_service.get_overrides_by_risk(
            risk_id=risk_id,
            is_active=True,
        )

        data = []

        for override in overrides:
            data.append(
                {
                    "id": str(override["_id"]),
                    "risk_id": override["risk_id"],
                    "destination_id": override["destination_id"],
                    "overrides": override.get(
                        "overrides",
                        {},
                    ),
                    "is_active": override.get(
                        "is_active",
                        True,
                    ),
                    "created_at": override.get(
                        "created_at"
                    ),
                    "updated_at": override.get(
                        "updated_at"
                    ),
                }
            )

        return {
            "success": True,
            "data": data,
            "count": len(data),
        }

    except HTTPException:
        raise

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch risk destination overrides",
        ) from exc




@router.delete(
    "/{risk_id}/destinations/{destination_id}/override",
    status_code=status.HTTP_200_OK,
)
async def disable_risk_destination_override(
    risk_id: str,
    destination_id: str,
    service: RiskDestinationOverrideService = Depends(
        get_risk_destination_override_service
    ),
):
    try:
        # Service layer handles repository interaction.
        override = await service.disable_override(
            risk_id=risk_id,
            destination_id=destination_id,
        )

        if not override:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Risk destination override not found",
            )

        return {
            "success": True,
            "message": "Risk destination override disabled successfully",
            "risk_id": risk_id,
            "destination_id": destination_id,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to disable risk destination override",
        ) from exc