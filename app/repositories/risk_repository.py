class RiskRepository:

    def __init__(self, database):
        self.collection = database["risks"]

    async def get_all_risks(
        self,
        industry_slug: str | None = None,
        severity: str | None = None,
        is_active: bool | None = True
    ):
        query = {}

        if industry_slug:
            query["industry_slug"] = industry_slug

        if severity:
            query["severity"] = severity

        if is_active is not None:
            query["is_active"] = is_active

        risks = []
        cursor = self.collection.find(query).sort([
            ("created_at", -1),
            ("_id", -1)
        ])

        async for risk in cursor:
            risks.append(risk)

        return risks

    async def get_risk_by_id(self, risk_id: str):
        return await self.collection.find_one({
            "risk_id": risk_id
        })

    async def get_risks_by_industry(
        self,
        industry_slug: str,
        is_active: bool | None = True
    ):
        return await self.get_all_risks(
            industry_slug=industry_slug,
            is_active=is_active
        )
