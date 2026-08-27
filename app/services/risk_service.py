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
