from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SlackNormalizedInteraction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    platform: Literal["slack"] = "slack"
    interaction_type: Literal["block_action"] = "block_action"
    risk_id: str = Field(alias="riskId")
    action_key: Literal["view_details", "mitigation_plan"] = Field(
        alias="actionKey"
    )
    action_id: Literal["view_details", "mitigation_plan"] = Field(
        alias="actionId"
    )
    response_url: str = Field(alias="responseUrl")
    user_id: str = Field(alias="userId")
    channel_id: str = Field(alias="channelId")
    channel_name: str | None = Field(default=None, alias="channelName")
