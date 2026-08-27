from pydantic import BaseModel, ConfigDict


class RiskDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    risk_id: str


class RiskListResponse(BaseModel):
    success: bool = True
    data: list[RiskDocument]


class RiskDetailResponse(BaseModel):
    success: bool = True
    data: RiskDocument
