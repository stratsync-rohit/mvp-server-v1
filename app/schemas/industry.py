from pydantic import BaseModel

from app.schemas.risk import RiskDocument


class IndustryResponse(BaseModel):
    slug: str
    name: str
    risk_count: int


class IndustryListResponse(BaseModel):
    success: bool = True
    data: list[IndustryResponse]


class IndustryRiskListResponse(BaseModel):
    success: bool = True
    data: list[RiskDocument]
