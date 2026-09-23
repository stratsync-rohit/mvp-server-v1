from pydantic import BaseModel


class SlackConnectUrlData(BaseModel):
    connect_url: str


class SlackConnectUrlResponse(BaseModel):
    success: bool = True
    data: SlackConnectUrlData
