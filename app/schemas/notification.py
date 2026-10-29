from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.risk import RiskCreate


class NotificationTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_id: str = Field(min_length=1)
    destination_id: str = Field(min_length=1)

    @field_validator("risk_id", "destination_id")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be empty")
        return value


class NotificationTriggerData(BaseModel):
    notification_id: str
    risk_id: str
    destination_id: str
    team_name: str
    channel_name: str | None = None
    status: str
    sent_at: datetime


class NotificationTriggerResponse(BaseModel):
    success: bool = True
    message: str
    data: NotificationTriggerData


class TeamsPayloadPreviewRequest(BaseModel):
    """An unsaved or currently edited risk to render without delivery."""

    model_config = ConfigDict(extra="forbid")

    risk: RiskCreate


class TeamsPayloadPreviewResponse(BaseModel):
    bytes: int
    kb: float
    limit_bytes: int
    limit_kb: int
    too_large: bool
    measurement: Literal["rendered-teams-payload"]


class NotificationHistoryItem(BaseModel):
    id: str
    risk_id: str
    risk_title: str
    destination_id: str
    client_id: str
    team_name: str
    channel_name: str | None = None
    severity: str | None = None
    status: str
    failure_reason: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class NotificationHistoryResponse(BaseModel):
    success: bool = True
    data: list[NotificationHistoryItem]
