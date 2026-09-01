from urllib.parse import urlparse


def parse_slack_channel_link(channel_link: str) -> dict:
    """Parse a V1 Slack channel link without trusting client metadata."""
    result = {"workspace_domain": None, "channel_id": None}

    try:
        parsed = urlparse(channel_link.strip())
        hostname = (parsed.hostname or "").lower()

        if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
            return result
        if parsed.port not in (None, 443):
            return result
        if not hostname.endswith(".slack.com"):
            return result

        workspace_domain = hostname.removesuffix(".slack.com")
        if not workspace_domain or "." in workspace_domain:
            return result

        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2 or path_parts[0] != "archives":
            return result

        channel_id = path_parts[1].strip()
        if not channel_id:
            return result

        result["workspace_domain"] = workspace_domain
        result["channel_id"] = channel_id
        return result
    except (TypeError, ValueError):
        return result


def is_valid_slack_webhook_url(webhook_url: str) -> bool:
    """Validate a Slack Incoming Webhook URL without exposing its value."""
    try:
        parsed = urlparse(webhook_url.strip())
        if parsed.scheme.lower() != "https":
            return False
        if (parsed.hostname or "").lower() != "hooks.slack.com":
            return False
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if parsed.query or parsed.fragment:
            return False

        path_parts = parsed.path.strip("/").split("/")
        return (
            len(path_parts) == 4
            and path_parts[0] == "services"
            and all(path_parts[1:])
        )
    except (TypeError, ValueError):
        return False
