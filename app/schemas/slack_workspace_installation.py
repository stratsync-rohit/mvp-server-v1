from pydantic import BaseModel


class SlackIncomingWebhookMetadata(BaseModel):
    """Metadata returned by Slack for an optional incoming webhook."""

    channel: str | None = None
    channel_id: str | None = None
    configuration_url: str | None = None
    url: str | None = None


class SlackWorkspaceInstallation(BaseModel):
    """Internal installation record, including values stored privately."""

    client_id: str | None = None
    slack_team_id: str
    slack_team_name: str
    enterprise_id: str | None = None
    app_id: str
    bot_user_id: str | None = None
    access_token: str
    token_type: str = "bot"
    scope: str | None = None
    is_enterprise_install: bool = False
    is_active: bool = True
    incoming_webhook: SlackIncomingWebhookMetadata | None = None


class SlackWorkspaceInstallationData(BaseModel):
    installation_id: str
    destination_id: str | None = None
    workspace_id: str
    workspace_name: str
    channel_id: str | None = None
    channel_name: str | None = None
    is_active: bool


class SlackOAuthCallbackResponse(BaseModel):
    success: bool = True
    message: str
    data: SlackWorkspaceInstallationData
