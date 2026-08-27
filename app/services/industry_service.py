class IndustryService:

    def __init__(self, industry_repository):
        self.industry_repository = industry_repository

    async def get_industries(self):
        return await self.industry_repository.get_industries()
