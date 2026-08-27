from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(..., description="Name of the client", max_length=100, min_length=1, examples=["ABC Shipping"])

class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Name of the client", max_length=100, min_length=1, examples=["ABC Shipping"])
    is_active: Optional[bool] = Field(None, description="Status of the client", examples=[True, False])

class ClientResponse(BaseModel):
    id: str
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClientCreateResponse(BaseModel):
    success: bool = True
    data: ClientResponse


class ClientUpdateResponse(BaseModel):
    success: bool = True
    message: str
    data: ClientResponse


class ClientListResponse(BaseModel):
    success: bool = True
    data: list[ClientResponse]
