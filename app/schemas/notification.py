from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
