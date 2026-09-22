from copy import deepcopy

from app.repositories.risk_destination_override_repository import (
    RiskDestinationOverrideRepository,
)


class RiskDestinationOverrideService:

    def __init__(
        self,
        repository: RiskDestinationOverrideRepository,
    ):
        self.repository = repository

    # =====================================================
    # GET SINGLE OVERRIDE
    # =====================================================

    async def get_override(
        self,
        risk_id: str,
        destination_id: str,
    ):
        return await self.repository.get_by_risk_and_destination(
            risk_id=risk_id,
            destination_id=destination_id,
        )

    # =====================================================
    # CREATE / UPDATE OVERRIDE
    # =====================================================

    async def upsert_override(
        self,
        risk_id: str,
        destination_id: str,
        overrides: dict,
        is_active: bool = True,
    ):
        return await self.repository.upsert_override(
            risk_id=risk_id,
            destination_id=destination_id,
            document={
                "overrides": overrides,
                "is_active": is_active,
            },
        )

    # =====================================================
    # LIST OVERRIDES FOR RISK
    # =====================================================

    async def get_overrides_by_risk(
        self,
        risk_id: str,
        is_active: bool | None = True,
    ):
        return await self.repository.get_overrides_by_risk(
            risk_id=risk_id,
            is_active=is_active,
        )

    # =====================================================
    # DISABLE OVERRIDE
    # =====================================================

    async def disable_override(
        self,
        risk_id: str,
        destination_id: str,
    ):
        return await self.repository.disable_override(
            risk_id=risk_id,
            destination_id=destination_id,
        )

    # =====================================================
    # RESOLVE FINAL RISK
    # =====================================================

    async def resolve_risk(
        self,
        risk: dict,
        destination_id: str,
    ):
        resolved_risk = deepcopy(risk)

        override = await self.get_override(
            risk_id=risk["risk_id"],
            destination_id=destination_id,
        )

        if not override:
            return resolved_risk

        return self._deep_merge(
            resolved_risk,
            override.get(
                "overrides",
                {},
            ),
        )

    # =====================================================
    # DEEP MERGE
    # =====================================================

    def _deep_merge(
        self,
        base: dict,
        override: dict,
    ):
        for key, value in override.items():

            if (
                isinstance(value, dict)
                and isinstance(base.get(key), dict)
            ):
                self._deep_merge(
                    base[key],
                    value,
                )

            else:
                # Lists and scalar values replace
                # the corresponding base value.
                base[key] = deepcopy(value)

        return base