import hashlib
import hmac
import time


SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS = 5 * 60


def verify_slack_signature(
    *,
    raw_body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str,
) -> bool:
    if not timestamp or not signature:
        return False

    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False

    if (
        abs(time.time() - timestamp_value)
        > SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS
    ):
        return False

    signature_base = (
        b"v0:"
        + timestamp.encode("utf-8")
        + b":"
        + raw_body
    )
    expected_signature = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        signature_base,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)
