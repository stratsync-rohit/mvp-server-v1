from datetime import datetime, timezone


def calculate_elapsed_time(reported_date: datetime | None) -> str | None:
    """Return the completed time since a timezone-aware reported date.

    Invalid, timezone-naive, missing, and future values intentionally produce
    ``None`` so legacy or malformed stored records cannot break retrieval.
    """
    if not isinstance(reported_date, datetime):
        return None

    if (
        reported_date.tzinfo is None
        or reported_date.utcoffset() is None
    ):
        return None

    now = datetime.now(timezone.utc)
    elapsed_seconds = (
        now - reported_date.astimezone(timezone.utc)
    ).total_seconds()

    if elapsed_seconds < 0:
        return None

    completed_hours = int(elapsed_seconds // 3600)
    days, hours = divmod(completed_hours, 24)

    if days == 0:
        return f"{hours} hours"

    day_label = "day" if days == 1 else "days"
    return f"{days} {day_label} {hours} hours"
