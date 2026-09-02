"""
Central place for FastAPI dependency-injection wiring. Keeps API route
modules free of construction logic - they just declare what they need.

Using `Depends(...)` chains (rather than calling helpers directly) means
tests can override any single dependency (e.g. swap the real database for
a test one, or the real N8nService for a mock) via
`app.dependency_overrides`.
"""
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.database import get_database
from app.repositories.client_repository import ClientRepository
from app.repositories.industry_repository import IndustryRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.slack_destination_repository import SlackDestinationRepository
from app.repositories.teams_channel_repository import TeamsChannelRepository
from app.services.client_service import ClientService
from app.services.dashboard_service import DashboardService
from app.services.industry_service import IndustryService
from app.services.n8n_service import N8nService
from app.services.notification_service import NotificationService
from app.services.risk_service import RiskService
from app.services.slack_interaction_service import SlackInteractionService
from app.services.teams_channel_service import TeamsChannelService


def get_client_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> ClientRepository:
    return ClientRepository(database)


def get_teams_channel_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> TeamsChannelRepository:
    return TeamsChannelRepository(database)


def get_slack_destination_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> SlackDestinationRepository:
    return SlackDestinationRepository(database)


def get_risk_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> RiskRepository:
    return RiskRepository(database)


def get_industry_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> IndustryRepository:
    return IndustryRepository(database)


def get_notification_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> NotificationRepository:
    return NotificationRepository(database)


def get_client_service(
    repository: ClientRepository = Depends(get_client_repository),
) -> ClientService:
    return ClientService(repository)


def get_dashboard_service(
    client_repository: ClientRepository = Depends(get_client_repository),
    teams_channel_repository: TeamsChannelRepository = Depends(
        get_teams_channel_repository
    ),
    notification_repository: NotificationRepository = Depends(
        get_notification_repository
    ),
) -> DashboardService:
    return DashboardService(
        client_repository=client_repository,
        teams_channel_repository=teams_channel_repository,
        notification_repository=notification_repository
    )


def get_risk_service(
    repository: RiskRepository = Depends(get_risk_repository),
    industry_repository: IndustryRepository = Depends(get_industry_repository),
) -> RiskService:
    return RiskService(repository, industry_repository)


def get_industry_service(
    repository: IndustryRepository = Depends(get_industry_repository),
) -> IndustryService:
    return IndustryService(repository)


def get_teams_channel_service(
    repository: TeamsChannelRepository = Depends(get_teams_channel_repository),
    client_repository: ClientRepository = Depends(get_client_repository),
    settings: Settings = Depends(get_settings),
) -> TeamsChannelService:
    return TeamsChannelService(
        teams_channel_repository=repository,
        client_repository=client_repository,
        n8n_service=N8nService(settings),
    )


def get_n8n_service(settings: Settings = Depends(get_settings)) -> N8nService:
    return N8nService(settings)


def get_slack_n8n_service(
    settings: Settings = Depends(get_settings),
) -> N8nService:
    return N8nService(settings, webhook_url=settings.slack_n8n_webhook_url)


def get_slack_interaction_service(
    settings: Settings = Depends(get_settings),
) -> SlackInteractionService:
    return SlackInteractionService(settings)


def get_slack_interaction_n8n_service(
    settings: Settings = Depends(get_settings),
) -> N8nService:
    return N8nService(
        settings, webhook_url=settings.slack_interaction_n8n_url
    )


def get_notification_service(
    notification_repository: NotificationRepository = Depends(
        get_notification_repository
    ),
    risk_repository: RiskRepository = Depends(get_risk_repository),
    teams_channel_repository: TeamsChannelRepository = Depends(
        get_teams_channel_repository
    ),
    slack_destination_repository: SlackDestinationRepository = Depends(
        get_slack_destination_repository
    ),
    client_repository: ClientRepository = Depends(get_client_repository),
    n8n_service: N8nService = Depends(get_n8n_service),
    slack_n8n_service: N8nService = Depends(get_slack_n8n_service),
) -> NotificationService:
    return NotificationService(
        notification_repository=notification_repository,
        risk_repository=risk_repository,
        teams_channel_repository=teams_channel_repository,
        slack_destination_repository=slack_destination_repository,
        client_repository=client_repository,
        n8n_service=n8n_service,
        slack_n8n_service=slack_n8n_service,
    )
