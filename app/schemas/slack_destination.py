from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SlackDestinationCreate(BaseModel):
    channel_link: str = Field(..., min_length=1)
    channel_name: str = Field(..., min_length=1, max_length=100)
    webhook_url: str = Field(..., min_length=1)


class SlackDestinationUpdate(BaseModel):
    channel_link: str | None = None
    channel_name: str | None = Field(default=None, max_length=100)
    webhook_url: str | None = None
    is_active: bool | None = None

    @field_validator("webhook_url", mode="before")
    @classmethod
    def normalize_blank_webhook(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class SlackDestinationResponse(BaseModel):
    id: str
    client_id: str
    workspace_domain: str
    channel_id: str
    channel_name: str
    channel_link: str
    webhook_configured: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SlackDestinationCreateResponse(BaseModel):
    success: bool = True
    data: SlackDestinationResponse


class SlackDestinationGetResponse(BaseModel):
    success: bool = True
    data: SlackDestinationResponse


class SlackDestinationListResponse(BaseModel):
    success: bool = True
    data: list[SlackDestinationResponse]


class SlackDestinationUpdateResponse(BaseModel):
    success: bool = True
    message: str
    data: SlackDestinationResponse


class SlackDestinationDeleteResponse(BaseModel):
    success: bool = True
    message: str
    data: SlackDestinationResponse


class SlackDestinationTestResponse(BaseModel):
    success: bool = True
    status: str
    message: str
