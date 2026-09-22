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
from app.repositories.risk_destination_override_repository import (
    RiskDestinationOverrideRepository,
)
from app.repositories.slack_destination_repository import (
    SlackDestinationRepository,
)
from app.repositories.slack_workspace_installation_repository import (
    SlackWorkspaceInstallationRepository,
)
from app.repositories.teams_channel_repository import (
    TeamsChannelRepository,
)

from app.services.client_service import ClientService
from app.services.dashboard_service import DashboardService
from app.services.industry_service import IndustryService
from app.services.n8n_service import N8nService
from app.services.notification_service import NotificationService
from app.services.risk_service import RiskService
from app.services.risk_destination_override_service import (
    RiskDestinationOverrideService,
)
from app.services.slack_destination_service import (
    SlackDestinationService,
)
from app.services.slack_oauth_service import SlackOAuthService
from app.services.slack_oauth_state_service import SlackOAuthStateService
from app.services.slack_workspace_installation_service import (
    SlackWorkspaceInstallationService,
)
from app.services.teams_channel_service import TeamsChannelService


# =========================================================
# REPOSITORIES
# =========================================================

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


def get_slack_workspace_installation_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> SlackWorkspaceInstallationRepository:
    return SlackWorkspaceInstallationRepository(database)


def get_risk_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> RiskRepository:
    return RiskRepository(database)


def get_risk_destination_override_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> RiskDestinationOverrideRepository:
    return RiskDestinationOverrideRepository(database)


def get_industry_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> IndustryRepository:
    return IndustryRepository(database)


def get_notification_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> NotificationRepository:
    return NotificationRepository(database)


# =========================================================
# CLIENT SERVICE
# =========================================================

def get_client_service(
    repository: ClientRepository = Depends(
        get_client_repository
    ),
) -> ClientService:
    return ClientService(repository)


# =========================================================
# DASHBOARD SERVICE
# =========================================================

def get_dashboard_service(
    client_repository: ClientRepository = Depends(
        get_client_repository
    ),
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
        notification_repository=notification_repository,
    )


# =========================================================
# RISK SERVICE
# =========================================================

def get_risk_service(
    repository: RiskRepository = Depends(
        get_risk_repository
    ),
    industry_repository: IndustryRepository = Depends(
        get_industry_repository
    ),
) -> RiskService:
    return RiskService(
        repository,
        industry_repository,
    )


# =========================================================
# RISK DESTINATION OVERRIDE SERVICE
# =========================================================

def get_risk_destination_override_service(
    repository: RiskDestinationOverrideRepository = Depends(
        get_risk_destination_override_repository
    ),
) -> RiskDestinationOverrideService:
    return RiskDestinationOverrideService(
        repository
    )


# =========================================================
# INDUSTRY SERVICE
# =========================================================

def get_industry_service(
    repository: IndustryRepository = Depends(
        get_industry_repository
    ),
) -> IndustryService:
    return IndustryService(repository)


# =========================================================
# TEAMS CHANNEL SERVICE
# =========================================================

def get_teams_channel_service(
    repository: TeamsChannelRepository = Depends(
        get_teams_channel_repository
    ),
    client_repository: ClientRepository = Depends(
        get_client_repository
    ),
    settings: Settings = Depends(
        get_settings
    ),
) -> TeamsChannelService:
    return TeamsChannelService(
        teams_channel_repository=repository,
        client_repository=client_repository,
        n8n_service=N8nService(settings),
    )


# =========================================================
# SLACK DESTINATION SERVICE
# =========================================================

def get_slack_destination_service(
    repository: SlackDestinationRepository = Depends(
        get_slack_destination_repository
    ),
    client_repository: ClientRepository = Depends(
        get_client_repository
    ),
    settings: Settings = Depends(
        get_settings
    ),
) -> SlackDestinationService:
    return SlackDestinationService(
        slack_destination_repository=repository,
        client_repository=client_repository,
        slack_n8n_service=N8nService(
            settings,
            webhook_url=settings.slack_n8n_webhook_url,
        ),
    )


# =========================================================
# SLACK OAUTH
# =========================================================

def get_slack_oauth_service(
    settings: Settings = Depends(get_settings),
) -> SlackOAuthService:
    return SlackOAuthService(settings)


def get_slack_oauth_state_service(
    settings: Settings = Depends(get_settings),
    client_repository: ClientRepository = Depends(get_client_repository),
) -> SlackOAuthStateService:
    return SlackOAuthStateService(
        settings=settings,
        client_repository=client_repository,
    )


def get_slack_workspace_installation_service(
    repository: SlackWorkspaceInstallationRepository = Depends(
        get_slack_workspace_installation_repository
    ),
    client_repository: ClientRepository = Depends(get_client_repository),
    destination_repository: SlackDestinationRepository = Depends(
        get_slack_destination_repository
    ),
) -> SlackWorkspaceInstallationService:
    return SlackWorkspaceInstallationService(
        repository=repository,
        client_repository=client_repository,
        destination_repository=destination_repository,
    )


# =========================================================
# N8N SERVICES
# =========================================================

def get_n8n_service(
    settings: Settings = Depends(
        get_settings
    ),
) -> N8nService:
    return N8nService(settings)


def get_slack_n8n_service(
    settings: Settings = Depends(
        get_settings
    ),
) -> N8nService:
    return N8nService(
        settings,
        webhook_url=settings.slack_n8n_webhook_url,
    )


# =========================================================
# NOTIFICATION SERVICE
# =========================================================

def get_notification_service(
    notification_repository: NotificationRepository = Depends(
        get_notification_repository
    ),
    risk_repository: RiskRepository = Depends(
        get_risk_repository
    ),
    teams_channel_repository: TeamsChannelRepository = Depends(
        get_teams_channel_repository
    ),
    slack_destination_repository: SlackDestinationRepository = Depends(
        get_slack_destination_repository
    ),
    client_repository: ClientRepository = Depends(
        get_client_repository
    ),
    risk_destination_override_service: RiskDestinationOverrideService = Depends(
        get_risk_destination_override_service
    ),
    n8n_service: N8nService = Depends(
        get_n8n_service
    ),
    slack_n8n_service: N8nService = Depends(
        get_slack_n8n_service
    ),
) -> NotificationService:
    return NotificationService(
        notification_repository=notification_repository,
        risk_repository=risk_repository,
        teams_channel_repository=teams_channel_repository,
        slack_destination_repository=slack_destination_repository,
        client_repository=client_repository,
        risk_destination_override_service=risk_destination_override_service,
        n8n_service=n8n_service,
        slack_n8n_service=slack_n8n_service,
    )
