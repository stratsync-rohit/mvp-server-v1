from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanonicalRiskModel(BaseModel):
    """
    Base model for builder-owned canonical risk data.

    extra="allow" is intentional so the generic risk schema can evolve
    without requiring a backend deployment for every new optional field.
    """

    model_config = ConfigDict(extra="allow")


# ============================================================
# COMMON MODELS
# ============================================================


class RiskSender(CanonicalRiskModel):
    name: str
    source: str
    risk_id: str | None = None
    timestamp: str = ""

    # Optional V2 fields such as:
    # time, context, etc. are preserved by extra="allow".


class RiskEntity(CanonicalRiskModel):
    type: str
    id: str
    name: str
    secondary: str | None = None


# ============================================================
# V1 MODELS
# ============================================================


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
    description: str | None = None
    owner: str


class RiskMitigation(CanonicalRiskModel):
    summary: str
    steps: list[RiskMitigationStep] = Field(default_factory=list)
    last_updated: str
    next_action: str


# ============================================================
# V2 GENERIC BLOCK MODELS
# ============================================================


class GenericBlock(CanonicalRiskModel):
    """
    Generic content block.

    Block-specific fields are intentionally not hard-coded here.

    Examples:

    text:
        {
            "type": "text",
            "title": "Incoming Stock",
            "text": "600 additional units due in 12 days",
            "status": "critical",
            "bold": true
        }

    key_value:
        {
            "type": "key_value",
            "title": "Inventory Snapshot",
            "items": [
                {
                    "label": "Last sold",
                    "value": "S$72/unit · 40 days ago"
                }
            ]
        }

    metrics:
        {
            "type": "metrics",
            "title": "Pricing Recommendation",
            "columns": 2,
            "items": [...]
        }

    table:
        {
            "type": "table",
            "title": "Customer Targets",
            "columns": [...],
            "rows": [...]
        }

    action_list:
        {
            "type": "action_list",
            "title": "Recommended Actions",
            "items": [...]
        }
    """

    type: str

    @field_validator("type")
    @classmethod
    def validate_block_type(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("block type must not be blank")

        return value


class GenericRiskView(CanonicalRiskModel):
    """
    Generic view used by schema_version=2.

    notification normally only needs blocks.

    details / mitigation may additionally contain:
    title
    subtitle
    action_label
    """

    title: str | None = None
    subtitle: str | None = None
    action_label: str | None = None

    blocks: list[GenericBlock] = Field(default_factory=list)


class RiskViews(CanonicalRiskModel):
    notification: GenericRiskView = Field(
        default_factory=GenericRiskView
    )

    details: GenericRiskView = Field(
        default_factory=GenericRiskView
    )

    mitigation: GenericRiskView = Field(
        default_factory=GenericRiskView
    )


# ============================================================
# CREATE MODEL
# ============================================================


class RiskCreate(CanonicalRiskModel):
    """
    Accepts both:

    V1 legacy/canonical risk:
        metrics
        details
        mitigation
        actions
        detected_time

    V2 generic risk:
        schema_version = 2
        views.notification.blocks
        views.details.blocks
        views.mitigation.blocks

    V1 fields remain supported for existing risks.
    """

    schema_version: int = 1

    # --------------------------------------------------------
    # Core fields
    # --------------------------------------------------------

    risk_id: str
    card_id: str

    industry_slug: str
    industry_name: str

    title: str
    severity: str
    severity_label: str

    subtitle: str = ""
    summary: str = ""

    sender: RiskSender
    entity: RiskEntity

    # --------------------------------------------------------
    # V1 fields
    # --------------------------------------------------------

    metrics: list[RiskMetric] | None = None
    details: RiskDetails | None = None
    mitigation: RiskMitigation | None = None
    actions: list[dict[str, Any]] | None = None
    detected_time: str | None = None

    # --------------------------------------------------------
    # V2 fields
    # --------------------------------------------------------

    views: RiskViews | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    is_active: bool = True
    status: str = "active"

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    @field_validator("risk_id")
    @classmethod
    def validate_risk_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("risk_id must not be blank")

        return value

    @field_validator("card_id")
    @classmethod
    def validate_card_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("card_id must not be blank")

        return value

    @field_validator("industry_slug")
    @classmethod
    def validate_industry_slug(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("industry_slug must not be blank")

        return value

    @field_validator("industry_name")
    @classmethod
    def validate_industry_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("industry_name must not be blank")

        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("title must not be blank")

        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("severity must not be blank")

        return value

    @model_validator(mode="after")
    def validate_schema_version(self):
        """
        V1:
            Existing legacy structure is accepted.

        V2:
            views must exist.

        Future schema versions are rejected until explicitly supported.
        """

        if self.schema_version == 1:
            return self

        if self.schema_version == 2:
            if self.views is None:
                raise ValueError(
                    "views is required when schema_version is 2"
                )

            return self

        raise ValueError(
            f"Unsupported schema_version: {self.schema_version}"
        )


# ============================================================
# RESPONSE MODELS
# ============================================================


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