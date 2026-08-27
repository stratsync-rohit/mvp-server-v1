from datetime import datetime

from pydantic import BaseModel


class DashboardSummaryData(BaseModel):
    total_clients: int
    active_teams_channels: int
    inactive_channels: int
    notifications_sent: int


class DashboardClientData(BaseModel):
    id: str
    name: str
    code: str
    is_active: bool


class ClientDashboardSummaryData(BaseModel):
    client: DashboardClientData
    active_teams: int
    active_teams_channels: int
    inactive_channels: int
    notifications_sent: int


class DashboardSummaryResponse(BaseModel):
    success: bool = True
    data: DashboardSummaryData | ClientDashboardSummaryData


class RecentIntegrationData(BaseModel):
    id: str
    client_id: str
    client_name: str
    team_name: str
    channel_name: str | None = None
    is_active: bool
    webhook_configured: bool
    created_at: datetime | None = None


class RecentIntegrationsResponse(BaseModel):
    success: bool = True
    data: list[RecentIntegrationData]
