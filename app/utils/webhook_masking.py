"""
Helpers for handling the secret Teams webhook URL safely.

Preferred pattern across the API is to NOT return any form of the webhook
URL at all - just a `webhook_configured: bool`. `mask_webhook_url` is kept
available for the rare internal/debugging case (e.g. structured log during
local development) where a human needs a hint without the full secret, but
it is not used by any public-facing response in this codebase.
"""


def mask_webhook_url(url: str | None) -> str | None:
    """
    Return a masked version of a webhook URL, e.g.:
        https://prod-123.westus.logic.azure.com/workflows/abc...xyz
        -> https://prod-123.westus...://***MASKED***
    Never returns enough of the URL to be usable.
    """
    if not url:
        return None
    try:
        scheme_sep = url.find("://")
        if scheme_sep == -1:
            return "***MASKED***"
        scheme = url[: scheme_sep + 3]
        rest = url[scheme_sep + 3 :]
        host = rest.split("/", 1)[0]
        return f"{scheme}{host}/***MASKED***"
    except Exception:
        return "***MASKED***"


def webhook_configured(url: str | None) -> bool:
    """True if a non-empty webhook URL is set."""
    return bool(url and url.strip())
