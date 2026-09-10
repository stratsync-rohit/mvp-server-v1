from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.schemas.risk import RiskCreate
from app.utils.mongo_serializer import serialize_mongo_document


class RiskService:

    def __init__(self, risk_repository, industry_repository):
        self.risk_repository = risk_repository
        self.industry_repository = industry_repository

    async def get_all_risks(
        self,
        industry_slug: str | None = None,
        severity: str | None = None,
        is_active: bool | None = True
    ):
        risks = await self.risk_repository.get_all_risks(
            industry_slug=industry_slug,
            severity=severity,
            is_active=is_active
        )
        return [serialize_mongo_document(risk) for risk in risks]

    async def get_risk_by_id(self, risk_id: str):
        risk = await self.risk_repository.get_risk_by_id(risk_id)

        if risk is None:
            raise ValueError("Risk not found")

        return serialize_mongo_document(risk)

    async def get_risks_by_industry(self, industry_slug: str):
        if not await self.industry_repository.exists(industry_slug):
            raise ValueError("Industry not found")

        risks = await self.risk_repository.get_risks_by_industry(
            industry_slug=industry_slug,
            is_active=True
        )
        return [serialize_mongo_document(risk) for risk in risks]

    async def create_risk(self, payload: RiskCreate):
        # Preserve the builder payload shape instead of materializing omitted
        # optional fields as null/default values.
        document = payload.model_dump(mode="python", exclude_unset=True)

        # These fields are always owned by the server, even if supplied as extras.
        document.pop("_id", None)
        document.pop("created_at", None)
        document.pop("updated_at", None)

        self._normalize_canonical_document(document, document["risk_id"])

        existing = await self.risk_repository.get_risk_by_risk_id(
            document["risk_id"]
        )
        if existing is not None:
            raise ConflictError("Risk ID already exists")

        now = datetime.now(timezone.utc)
        document["created_at"] = now
        document["updated_at"] = now

        try:
            return await self.risk_repository.create_risk(document)
        except DuplicateKeyError as exc:
            raise ConflictError("Risk ID already exists") from exc

    async def update_risk(self, risk_id: str, payload: RiskCreate):
        if payload.risk_id != risk_id:
            raise ValidationAppError("Risk ID cannot be changed")

        existing = await self.risk_repository.get_risk_by_risk_id(risk_id)
        if existing is None:
            raise NotFoundError("Risk not found")

        document = payload.model_dump(mode="python", exclude_unset=True)
        document.pop("_id", None)
        document.pop("created_at", None)
        document.pop("updated_at", None)
        self._normalize_canonical_document(document, risk_id)
        document["updated_at"] = datetime.now(timezone.utc)

        updated = await self.risk_repository.update_risk_by_risk_id(
            risk_id, document
        )
        if updated is None:
            # The record may have been deleted between the read and update.
            raise NotFoundError("Risk not found")
        return updated

    async def delete_risk(self, risk_id: str) -> None:
        deleted = await self.risk_repository.delete_risk_by_risk_id(risk_id)
        if not deleted:
            raise NotFoundError("Risk not found")

    @staticmethod
    def _normalize_canonical_document(document: dict, risk_id: str) -> None:
        document["sender"]["risk_id"] = risk_id
        real_steps = []
        for step in document["mitigation"]["steps"]:
            is_placeholder = (
                step["title"] == "New mitigation step"
                and step["description"] == ""
                and step["owner"] == ""
            )
            if not is_placeholder:
                real_steps.append(step)

        for number, step in enumerate(real_steps, start=1):
            step["step"] = number
        document["mitigation"]["steps"] = real_steps
