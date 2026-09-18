from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


class TeamsChannelCreate(BaseModel):
    member_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        examples=["John Tan"],
    )

    team_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        examples=["Operations Team"],
    )

    channel_url: HttpUrl = Field(
        ...,
        examples=[
            "https://teams.microsoft.com/l/channel/..."
        ],
    )

    teams_webhook_url: HttpUrl = Field(
        ...,
        examples=[
            "https://..."
        ],
    )

    @field_validator("member_name", "team_name")
    @classmethod
    def normalize_names(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Value must not be blank")

        return value


class TeamsChannelUpdate(BaseModel):
    member_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    team_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    channel_url: HttpUrl | None = None
    teams_webhook_url: HttpUrl | None = None
    is_active: bool | None = None

    @field_validator("member_name", "team_name")
    @classmethod
    def normalize_names(cls, value: str | None):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Value must not be blank")

        return value

    @field_validator("teams_webhook_url", mode="before")
    @classmethod
    def normalize_blank_webhook(cls, value):
        if isinstance(value, str) and not value.strip():
            return None

        return value


class TeamsChannelResponse(BaseModel):
    id: str
    client_id: str

    member_name: str | None = None

    team_name: str
    channel_name: str | None = None

    channel_url: str

    tenant_id: str | None = None
    team_id: str | None = None
    channel_id: str | None = None

    webhook_configured: bool

    is_active: bool

    created_at: datetime
    updated_at: datetime


class TeamsChannelCreateResponse(BaseModel):
    success: bool = True
    data: TeamsChannelResponse


class TeamsChannelGetResponse(BaseModel):
    success: bool = True
    data: TeamsChannelResponse


class TeamsChannelUpdateResponse(BaseModel):
    success: bool = True
    message: str
    data: TeamsChannelResponse


class TeamsChannelTestData(BaseModel):
    destination_id: str
    member_name: str | None = None
    team_name: str
    channel_name: str


class TeamsChannelTestResponse(BaseModel):
    success: bool = True
    message: str
    data: TeamsChannelTestData