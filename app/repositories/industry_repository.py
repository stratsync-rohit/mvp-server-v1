class IndustryRepository:

    def __init__(self, database):
        self.collection = database["industries"]
        self.risk_collection = database["risks"]

    async def get_industries(self):
        count_pipeline = [
            {
                "$match": {
                    "is_active": True,
                    "industry_slug": {"$type": "string", "$ne": ""}
                }
            },
            {
                "$group": {
                    "_id": "$industry_slug",
                    "risk_count": {"$sum": 1}
                }
            }
        ]
        count_documents = await self.risk_collection.aggregate(
            count_pipeline
        ).to_list(length=None)
        risk_counts = {
            document["_id"]: document["risk_count"]
            for document in count_documents
        }

        industries = []
        cursor = self.collection.find({"is_active": True}).sort("name", 1)

        async for industry in cursor:
            industries.append({
                "slug": industry["slug"],
                "name": industry["name"],
                "risk_count": risk_counts.get(industry["slug"], 0)
            })

        return industries

    async def exists(self, industry_slug: str) -> bool:
        industry = await self.collection.find_one(
            {"slug": industry_slug, "is_active": True},
            {"_id": 1}
        )
        return industry is not None
