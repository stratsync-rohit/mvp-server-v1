from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SlackDestinationCreate(BaseModel):

    member_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        examples=["John Tan"],
    )

    channel_link: str = Field(
        ...,
        min_length=1,
    )

    channel_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    webhook_url: str = Field(
        ...,
        min_length=1,
    )

    @field_validator("member_name", "channel_name")
    @classmethod
    def normalize_names(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Value must not be blank")

        return value


class SlackDestinationUpdate(BaseModel):

    member_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    channel_link: str | None = None

    channel_name: str | None = Field(
        default=None,
        max_length=100,
    )

    webhook_url: str | None = None

    is_active: bool | None = None

    @field_validator("member_name", "channel_name")
    @classmethod
    def normalize_names(cls, value: str | None):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Value must not be blank")

        return value

    @field_validator("webhook_url", mode="before")
    @classmethod
    def normalize_blank_webhook(cls, value):
        if isinstance(value, str) and not value.strip():
            return None

        return value


class SlackDestinationResponse(BaseModel):

    id: str

    client_id: str

    # Optional in response for backward compatibility
    # with existing MongoDB destinations.
    member_name: str | None = None

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