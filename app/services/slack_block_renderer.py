from __future__ import annotations

import json
from typing import Any


# ============================================================
# SLACK LIMITS / HELPERS
# ============================================================

MAX_SECTION_TEXT = 3000
MAX_FIELD_TEXT = 2000
MAX_BLOCKS = 50
MAX_ACTION_VALUE = 2000
MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 20


def _safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text or fallback


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _truncate(text: str, limit: int) -> str:
    text = _safe_text(text)

    if len(text) <= limit:
        return text

    return text[: max(0, limit - 1)].rstrip() + "…"


def _mrkdwn(text: Any) -> dict[str, str]:
    return {
        "type": "mrkdwn",
        "text": _truncate(
            _safe_text(text),
            MAX_SECTION_TEXT,
        ),
    }


def _plain_text(text: Any) -> dict[str, Any]:
    return {
        "type": "plain_text",
        "text": _truncate(
            _safe_text(text),
            75,
        ),
        "emoji": False,
    }


def _escape_mrkdwn(value: Any) -> str:
    text = _safe_text(value)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _heading(title: Any) -> dict[str, Any] | None:
    title = _safe_text(title)

    if not title:
        return None

    return {
        "type": "section",
        "text": _mrkdwn(
            f"*{_escape_mrkdwn(title.upper())}*"
        ),
    }


def _divider() -> dict[str, str]:
    return {
        "type": "divider",
    }


# ============================================================
# GENERIC BLOCK RENDERERS
# ============================================================

def _render_text_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(block.get("title"))

    text = _safe_text(
        block.get("text")
        or block.get("value")
        or block.get("content")
    )

    if title:
        heading = _heading(title)

        if heading:
            result.append(heading)

    if text:
        rendered_text = _escape_mrkdwn(text)

        if block.get("bold") is True:
            rendered_text = f"*{rendered_text}*"

        result.append(
            {
                "type": "section",
                "text": _mrkdwn(rendered_text),
            }
        )

    return result


def _render_callout_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(block.get("title"))

    text = _safe_text(
        block.get("text")
        or block.get("value")
        or block.get("content")
    )

    if title:
        heading = _heading(title)

        if heading:
            result.append(heading)

    if not text:
        return result

    result.append(
        {
            "type": "section",
            "text": _mrkdwn(
                f"*{_escape_mrkdwn(text)}*"
            ),
        }
    )

    return result


def _render_key_value_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(block.get("title"))

    if title:
        heading = _heading(title)

        if heading:
            result.append(heading)

    fields: list[dict[str, str]] = []

    for item in _safe_list(block.get("items")):
        if not isinstance(item, dict):
            continue

        label = _safe_text(
            item.get("label")
            or item.get("key")
            or item.get("title")
        )

        value = _safe_text(
            item.get("value"),
            "-",
        )

        if not label:
            continue

        text = (
            f"*{_escape_mrkdwn(label)}*\n"
            f"{_escape_mrkdwn(value)}"
        )

        fields.append(
            {
                "type": "mrkdwn",
                "text": _truncate(
                    text,
                    MAX_FIELD_TEXT,
                ),
            }
        )

    for index in range(0, len(fields), 10):
        chunk = fields[index:index + 10]

        if chunk:
            result.append(
                {
                    "type": "section",
                    "fields": chunk,
                }
            )

    return result


def _render_metrics_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(
        block.get("title"),
        "Key Metrics",
    )

    heading = _heading(title)

    if heading:
        result.append(heading)

    fields: list[dict[str, str]] = []

    for metric in _safe_list(block.get("items")):
        if not isinstance(metric, dict):
            continue

        label = _safe_text(
            metric.get("label")
            or metric.get("name")
            or metric.get("key")
        )

        value = _safe_text(
            metric.get("value"),
            "-",
        )

        if not label:
            continue

        text = (
            f"*{_escape_mrkdwn(label)}*\n"
            f"{_escape_mrkdwn(value)}"
        )

        fields.append(
            {
                "type": "mrkdwn",
                "text": _truncate(
                    text,
                    MAX_FIELD_TEXT,
                ),
            }
        )

    for index in range(0, len(fields), 10):
        chunk = fields[index:index + 10]

        if chunk:
            result.append(
                {
                    "type": "section",
                    "fields": chunk,
                }
            )

    return result


def _render_bullet_list_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(block.get("title"))

    if title:
        heading = _heading(title)

        if heading:
            result.append(heading)

    lines: list[str] = []

    for item in _safe_list(block.get("items")):
        if isinstance(item, dict):
            text = _safe_text(
                item.get("text")
                or item.get("title")
                or item.get("value")
                or item.get("description")
            )
        else:
            text = _safe_text(item)

        if not text:
            continue

        lines.append(
            f"• {_escape_mrkdwn(text)}"
        )

    if lines:
        result.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    "\n".join(lines)
                ),
            }
        )

    return result


def _render_numbered_list_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(block.get("title"))

    if title:
        heading = _heading(title)

        if heading:
            result.append(heading)

    lines: list[str] = []

    for index, item in enumerate(
        _safe_list(block.get("items")),
        start=1,
    ):
        if isinstance(item, dict):
            text = _safe_text(
                item.get("text")
                or item.get("title")
                or item.get("value")
                or item.get("description")
            )
        else:
            text = _safe_text(item)

        if not text:
            continue

        lines.append(
            f"{index}. {_escape_mrkdwn(text)}"
        )

    if lines:
        result.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    "\n".join(lines)
                ),
            }
        )

    return result


# ============================================================
# NATIVE SLACK TABLE
# ============================================================

def _table_cell(
    value: Any,
    *,
    bold: bool = False,
) -> dict[str, str]:

    text = _safe_text(value, "-")

    if bold:
        text = f"*{_escape_mrkdwn(text)}*"
    else:
        text = _escape_mrkdwn(text)

    return {
        "type": "raw_text",
        "text": text,
    }


def _render_table_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(block.get("title"))

    if title:
        heading = _heading(title)

        if heading:
            result.append(heading)

    columns = [
        column
        for column in _safe_list(block.get("columns"))
        if isinstance(column, dict)
    ][:MAX_TABLE_COLUMNS]

    rows = [
        row
        for row in _safe_list(block.get("rows"))
        if isinstance(row, dict)
    ][:MAX_TABLE_ROWS]

    if not columns or not rows:
        return result

    table_rows: list[list[dict[str, str]]] = []

    # --------------------------------------------------------
    # HEADER ROW
    # --------------------------------------------------------

    header_row: list[dict[str, str]] = []

    for column in columns:
        key = _safe_text(column.get("key"))

        label = _safe_text(
            column.get("label")
            or column.get("title")
            or key,
            "-",
        )

        header_row.append(
            _table_cell(
                label,
                bold=True,
            )
        )

    table_rows.append(header_row)

    # --------------------------------------------------------
    # DATA ROWS
    # --------------------------------------------------------

    for row in rows:
        rendered_row: list[dict[str, str]] = []

        for column in columns:
            key = _safe_text(column.get("key"))

            value = _safe_text(
                row.get(key),
                "-",
            )

            rendered_row.append(
                _table_cell(value)
            )

        table_rows.append(rendered_row)

    # --------------------------------------------------------
    # COLUMN SETTINGS
    # --------------------------------------------------------

    column_settings: list[dict[str, Any]] = []

    for column in columns:
        setting: dict[str, Any] = {
            "align": _safe_text(
                column.get("align"),
                "left",
            )
        }

        if setting["align"] not in {
            "left",
            "center",
            "right",
        }:
            setting["align"] = "left"

        column_settings.append(setting)

    result.append(
        {
            "type": "table",
            "rows": table_rows,
            "column_settings": column_settings,
        }
    )

    return result


def _render_action_list_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []

    title = _safe_text(
        block.get("title"),
        "Action Plan",
    )

    heading = _heading(title)

    if heading:
        result.append(heading)

    lines: list[str] = []

    for index, item in enumerate(
        _safe_list(block.get("items"))
    ):
        if isinstance(item, str):
            action_title = _safe_text(item)
            owner = ""
            status = ""
            order = index + 1

        elif isinstance(item, dict):
            action_title = _safe_text(
                item.get("title")
                or item.get("description")
                or item.get("action")
                or item.get("text")
            )

            if (
                not action_title
                and isinstance(item.get("step"), str)
            ):
                action_title = _safe_text(
                    item.get("step")
                )

            owner = _safe_text(
                item.get("owner")
            )

            status = _safe_text(
                item.get("status")
            )

            order_value = (
                item.get("order")
                if item.get("order") is not None
                else item.get("step")
            )

            if isinstance(
                order_value,
                (int, float),
            ):
                order = int(order_value)
            else:
                order = index + 1

        else:
            continue

        if not action_title:
            continue

        line = (
            f"*{order}.* "
            f"{_escape_mrkdwn(action_title)}"
        )

        metadata: list[str] = []

        if owner:
            metadata.append(
                f"Owner: {_escape_mrkdwn(owner)}"
            )

        if status:
            metadata.append(
                f"Status: {_escape_mrkdwn(status)}"
            )

        if metadata:
            line += (
                "\n"
                + " · ".join(metadata)
            )

        lines.append(line)

    if lines:
        result.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    "\n\n".join(lines)
                ),
            }
        )

    return result


def _render_divider_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:

    return [_divider()]


def _render_generic_block(
    block: Any,
) -> list[dict[str, Any]]:

    if not isinstance(block, dict):
        return []

    block_type = _safe_text(
        block.get("type")
    ).lower()

    renderers = {
        "text": _render_text_block,
        "callout": _render_callout_block,

        "key_value": _render_key_value_block,
        "key-value": _render_key_value_block,
        "keyvalue": _render_key_value_block,

        "metrics": _render_metrics_block,

        "bullet_list": _render_bullet_list_block,
        "bullet-list": _render_bullet_list_block,
        "bullets": _render_bullet_list_block,

        "numbered_list": _render_numbered_list_block,
        "numbered-list": _render_numbered_list_block,

        "table": _render_table_block,

        "action_list": _render_action_list_block,
        "action-list": _render_action_list_block,
        "actions": _render_action_list_block,

        "divider": _render_divider_block,
    }

    renderer = renderers.get(block_type)

    if renderer is None:
        return []

    return renderer(block)


def _render_blocks(
    blocks: Any,
) -> list[dict[str, Any]]:

    rendered: list[dict[str, Any]] = []

    for block in _safe_list(blocks):
        rendered.extend(
            _render_generic_block(block)
        )

        if len(rendered) >= MAX_BLOCKS:
            break

    return rendered[:MAX_BLOCKS]


# ============================================================
# INTERACTION ACTION VALUE
# ============================================================

def _action_value(
    risk_id: str,
    view: str,
) -> str:

    payload = {
        "risk_id": risk_id,
        "view": view,
    }

    value = json.dumps(
        payload,
        separators=(",", ":"),
    )

    return _truncate(
        value,
        MAX_ACTION_VALUE,
    )


# ============================================================
# SHARED HEADER / FOOTER
# ============================================================

def _build_header_blocks(
    risk: dict[str, Any],
) -> list[dict[str, Any]]:

    sender = _safe_dict(
        risk.get("sender")
    )

    source = _safe_text(
        sender.get("source")
        or sender.get("name"),
        "StratSync RRM",
    )

    title = _safe_text(
        risk.get("title"),
        "Risk Alert",
    )

    severity = _safe_text(
        risk.get("severity_label")
        or risk.get("severity"),
        "Unknown",
    )

    subtitle = _safe_text(
        risk.get("subtitle")
    )

    summary = _safe_text(
        risk.get("summary")
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "context",
            "elements": [
                _mrkdwn(
                    f"*{_escape_mrkdwn(source)}*"
                )
            ],
        },
        {
            "type": "header",
            "text": _plain_text(title),
        },
        {
            "type": "section",
            "text": _mrkdwn(
                f"*Severity:* {_escape_mrkdwn(severity)}"
            ),
        },
    ]

    if subtitle:
        blocks.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    _escape_mrkdwn(subtitle)
                ),
            }
        )

    if summary:
        blocks.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    _escape_mrkdwn(summary)
                ),
            }
        )

    return blocks


def _build_footer_block(
    risk: dict[str, Any],
) -> dict[str, Any]:

    sender = _safe_dict(
        risk.get("sender")
    )

    source = _safe_text(
        sender.get("source")
        or sender.get("name"),
        "StratSync RRM",
    )

    risk_id = _safe_text(
        sender.get("risk_id")
        or risk.get("risk_id")
    )

    timestamp = _safe_text(
        sender.get("timestamp")
        or sender.get("time")
    )

    parts = [
        _escape_mrkdwn(source)
    ]

    if risk_id:
        parts.append(
            f"Risk ID {_escape_mrkdwn(risk_id)}"
        )

    if timestamp:
        parts.append(
            _escape_mrkdwn(timestamp)
        )

    return {
        "type": "context",
        "elements": [
            _mrkdwn(
                " · ".join(parts)
            )
        ],
    }


# ============================================================
# V2
# ============================================================

def _is_schema_v2(
    risk: dict[str, Any],
) -> bool:

    version = risk.get(
        "schema_version"
    )

    try:
        version_number = int(version)
    except (TypeError, ValueError):
        version_number = 1

    return (
        version_number >= 2
        and isinstance(
            risk.get("views"),
            dict,
        )
    )


def _build_v2_notification(
    risk: dict[str, Any],
) -> dict[str, Any]:

    views = _safe_dict(
        risk.get("views")
    )

    notification_view = _safe_dict(
        views.get("notification")
    )

    details_view = _safe_dict(
        views.get("details")
    )

    mitigation_view = _safe_dict(
        views.get("mitigation")
    )

    risk_id = _safe_text(
        risk.get("risk_id")
    )

    blocks = _build_header_blocks(risk)

    rendered_notification = _render_blocks(
        notification_view.get("blocks")
    )

    blocks.extend(
        rendered_notification
    )

    blocks.append(
        _divider()
    )

    blocks.append(
        _build_footer_block(risk)
    )

    actions: list[dict[str, Any]] = []

    if (
        risk_id
        and _safe_list(
            details_view.get("blocks")
        )
    ):
        actions.append(
            {
                "type": "button",
                "text": _plain_text(
                    _safe_text(
                        details_view.get(
                            "action_label"
                        ),
                        "View Details",
                    )
                ),
                "action_id": "risk_view_details",
                "value": _action_value(
                    risk_id,
                    "details",
                ),
            }
        )

    if (
        risk_id
        and _safe_list(
            mitigation_view.get("blocks")
        )
    ):
        actions.append(
            {
                "type": "button",
                "text": _plain_text(
                    _safe_text(
                        mitigation_view.get(
                            "action_label"
                        ),
                        "Mitigation Plan",
                    )
                ),
                "action_id": "risk_view_mitigation",
                "value": _action_value(
                    risk_id,
                    "mitigation",
                ),
            }
        )

    if actions:
        blocks.append(
            {
                "type": "actions",
                "block_id": "risk_actions",
                "elements": actions,
            }
        )

    title = _safe_text(
        risk.get("title"),
        "Risk Alert",
    )

    severity = _safe_text(
        risk.get("severity_label")
        or risk.get("severity"),
        "Unknown",
    )

    return {
        "text": f"{title} · {severity}",
        "blocks": blocks[:MAX_BLOCKS],
    }


# ============================================================
# GENERIC INTERACTIVE VIEW
# ============================================================

def build_slack_risk_view_payload(
    risk: dict[str, Any],
    view_name: str,
) -> dict[str, Any]:

    risk = _safe_dict(risk)

    views = _safe_dict(
        risk.get("views")
    )

    view_name = _safe_text(
        view_name
    ).lower()

    if view_name not in {
        "notification",
        "details",
        "mitigation",
    }:
        view_name = "notification"

    if view_name == "notification":
        return build_slack_notification_payload(
            risk
        )

    view = _safe_dict(
        views.get(view_name)
    )

    if view_name == "details":
        default_title = "Risk Details"
        default_subtitle = (
            "Complete context and exposure information"
        )
    else:
        default_title = "Mitigation Plan"
        default_subtitle = (
            "Recommended actions to reduce risk"
        )

    title = _safe_text(
        view.get("title"),
        default_title,
    )

    subtitle = _safe_text(
        view.get("subtitle"),
        default_subtitle,
    )

    risk_id = _safe_text(
        risk.get("risk_id")
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": _plain_text(title),
        }
    ]

    if subtitle:
        blocks.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    _escape_mrkdwn(subtitle)
                ),
            }
        )

    blocks.append(
        _divider()
    )

    rendered = _render_blocks(
        view.get("blocks")
    )

    if rendered:
        blocks.extend(rendered)
    else:
        blocks.append(
            {
                "type": "section",
                "text": _mrkdwn(
                    "_No additional information is available._"
                ),
            }
        )

    blocks.append(
        _divider()
    )

    blocks.append(
        _build_footer_block(risk)
    )

    if risk_id:
        blocks.append(
            {
                "type": "actions",
                "block_id": "risk_navigation",
                "elements": [
                    {
                        "type": "button",
                        "text": _plain_text(
                            "Back to Alert"
                        ),
                        "action_id": "risk_view_notification",
                        "value": _action_value(
                            risk_id,
                            "notification",
                        ),
                    }
                ],
            }
        )

    return {
        "text": title,
        "blocks": blocks[:MAX_BLOCKS],
    }


# ============================================================
# PUBLIC API
# ============================================================

def build_slack_notification_payload(
    risk: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a StratSync risk document into a Slack
    Block Kit incoming-webhook payload.

    Schema V2 uses the generic views/block contract.

    Interactive buttons contain only compact navigation
    context. Risk details remain server-side.
    """

    risk = _safe_dict(risk)

    if _is_schema_v2(risk):
        return _build_v2_notification(
            risk
        )

    # Temporary V1 fallback.
    title = _safe_text(
        risk.get("title"),
        "Risk Alert",
    )

    severity = _safe_text(
        risk.get("severity_label")
        or risk.get("severity"),
        "Unknown",
    )

    blocks = _build_header_blocks(
        risk
    )

    metrics = [
        metric
        for metric in _safe_list(
            risk.get("metrics")
        )
        if isinstance(metric, dict)
    ]

    if metrics:
        blocks.extend(
            _render_metrics_block(
                {
                    "type": "metrics",
                    "title": "Key Metrics",
                    "items": metrics,
                }
            )
        )

    blocks.append(
        _divider()
    )

    blocks.append(
        _build_footer_block(
            risk
        )
    )

    return {
        "text": f"{title} · {severity}",
        "blocks": blocks[:MAX_BLOCKS],
    }