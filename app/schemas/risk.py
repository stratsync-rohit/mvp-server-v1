from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CanonicalRiskModel(BaseModel):
    """Base model for builder-owned canonical risk data."""

    model_config = ConfigDict(extra="allow")


class RiskSender(CanonicalRiskModel):
    name: str
    source: str
    risk_id: str | None = None
    timestamp: str


class RiskEntity(CanonicalRiskModel):
    type: str
    id: str
    name: str
    secondary: str | None = None


class RiskMetric(CanonicalRiskModel):
    key: str
    label: str
    value: str
    raw_value: str | int | float | bool | None = None
    type: str
    highlight: bool = False


class RiskDetailItem(CanonicalRiskModel):
    label: str
    value: str


class RiskDetails(CanonicalRiskModel):
    section_title: str
    items: list[RiskDetailItem] = Field(default_factory=list)
    underlying_exposure: list[str] = Field(default_factory=list)
    impact: list[str] = Field(default_factory=list)


class RiskMitigationStep(CanonicalRiskModel):
    step: int
    title: str
    description: str
    owner: str


class RiskMitigation(CanonicalRiskModel):
    summary: str
    steps: list[RiskMitigationStep] = Field(default_factory=list)
    last_updated: str
    next_action: str


class RiskCreate(CanonicalRiskModel):
    risk_id: str
    card_id: str
    industry_slug: str
    industry_name: str
    title: str
    severity: str
    severity_label: str
    subtitle: str
    summary: str
    sender: RiskSender
    entity: RiskEntity
    metrics: list[RiskMetric] = Field(default_factory=list)
    details: RiskDetails
    mitigation: RiskMitigation
    actions: list[dict[str, Any]] = Field(default_factory=list)
    detected_time: str
    is_active: bool
    status: str

    @field_validator("risk_id")
    @classmethod
    def validate_risk_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("risk_id must not be blank")
        return value


class RiskCreateResponse(BaseModel):
    message: str
    risk_id: str
    id: str = Field(alias="_id")

    model_config = ConfigDict(populate_by_name=True)


class RiskUpdateResponse(BaseModel):
    message: str
    risk_id: str


class RiskDeleteResponse(BaseModel):
    message: str
    risk_id: str


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
