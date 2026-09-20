from __future__ import annotations



from typing import Any





# ============================================================

# COMMON HELPERS

# ============================================================





def _safe_text(value: Any, fallback: str = "") -> str:

    if value is None:

        return fallback



    text = str(value).strip()

    return text or fallback





def _safe_list(value: Any) -> list[Any]:

    return value if isinstance(value, list) else []





def _safe_dict(value: Any) -> dict[str, Any]:

    return value if isinstance(value, dict) else {}





def _severity_color(severity: Any) -> str:

    value = _safe_text(severity).lower()



    if "critical" in value or "high" in value:

        return "Attention"



    if "medium" in value or "warning" in value:

        return "Warning"



    if "low" in value:

        return "Good"



    return "Default"





def _status_color(status: Any) -> str:

    value = _safe_text(status).lower()



    if value in {

        "critical",

        "high",

        "danger",

        "error",

        "failed",

        "negative",

    }:

        return "Attention"



    if value in {

        "medium",

        "warning",

        "warn",

        "pending",

    }:

        return "Warning"



    if value in {

        "low",

        "good",

        "success",

        "healthy",

        "positive",

        "ok",

    }:

        return "Good"



    if value in {"info", "accent"}:

        return "Accent"



    return "Default"





def _chunk(items: list[Any], size: int) -> list[list[Any]]:

    if size <= 0:

        return [items]



    return [

        items[index : index + size]

        for index in range(0, len(items), size)

    ]





def _section_heading(

    title: Any,

    spacing: str = "Medium",

) -> dict[str, Any] | None:

    text = _safe_text(title)



    if not text:

        return None



    return {

        "type": "TextBlock",

        "text": text.upper(),

        "weight": "Bolder",

        "size": "Small",

        "spacing": spacing,

        "wrap": True,

    }





# ============================================================

# GENERIC BLOCK RENDERER — SCHEMA V2

#

# Supported:

#   text

#   key_value

#   metrics

#   bullet_list

#   table

#   action_list

#

# Unknown block types are ignored safely.

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

        heading = _section_heading(title)



        if heading:

            result.append(heading)



    if text:

        text_block: dict[str, Any] = {

            "type": "TextBlock",

            "text": text,

            "wrap": True,

            "spacing": "Small" if title else "Medium",

        }



        if block.get("subtle") is True:

            text_block["isSubtle"] = True



        if block.get("bold") is True:

            text_block["weight"] = "Bolder"



        color = _status_color(block.get("status"))



        if color != "Default":

            text_block["color"] = color



        result.append(text_block)



    return result





def _render_key_value_block(

    block: dict[str, Any],

) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []



    title = _safe_text(block.get("title"))



    if title:

        heading = _section_heading(title)



        if heading:

            result.append(heading)



    items = _safe_list(block.get("items"))



    facts: list[dict[str, str]] = []



    for item in items:

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



        facts.append(

            {

                "title": label,

                "value": value,

            }

        )



    if facts:

        result.append(

            {

                "type": "FactSet",

                "facts": facts,

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



    items = [

        item

        for item in _safe_list(block.get("items"))

        if isinstance(item, dict)

    ]



    if not items:

        return result



    heading = _section_heading(title)



    if heading:

        result.append(heading)



    columns_per_row = block.get("columns", 2)



    try:

        columns_per_row = int(columns_per_row)

    except (TypeError, ValueError):

        columns_per_row = 2



    columns_per_row = max(

        1,

        min(columns_per_row, 3),

    )



    for group in _chunk(items, columns_per_row):

        columns: list[dict[str, Any]] = []



        for metric in group:

            label = _safe_text(

                metric.get("label")

                or metric.get("name")

                or metric.get("key")

            )



            value = _safe_text(

                metric.get("value"),

                "-",

            )



            status = metric.get("status")



            columns.append(

                {

                    "type": "Column",

                    "width": "stretch",

                    "items": [

                        {

                            "type": "TextBlock",

                            "text": label.upper(),

                            "size": "Small",

                            "isSubtle": True,

                            "wrap": True,

                        },

                        {

                            "type": "TextBlock",

                            "text": value,

                            "weight": "Bolder",

                            "size": "Medium",

                            "color": _status_color(status),

                            "wrap": True,

                        },

                    ],

                }

            )



        result.append(

            {

                "type": "ColumnSet",

                "spacing": "Small",

                "columns": columns,

            }

        )



    return result





def _render_bullet_list_block(

    block: dict[str, Any],

) -> list[dict[str, Any]]:

    result: list[dict[str, Any]] = []



    title = _safe_text(block.get("title"))



    if title:

        heading = _section_heading(title)



        if heading:

            result.append(heading)



    items = _safe_list(block.get("items"))



    for item in items:

        if isinstance(item, dict):

            text = _safe_text(

                item.get("text")

                or item.get("title")

                or item.get("value")

                or item.get("description")

            )



            status = item.get("status")

        else:

            text = _safe_text(item)

            status = None



        if not text:

            continue



        bullet: dict[str, Any] = {

            "type": "TextBlock",

            "text": f"• {text}",

            "wrap": True,

            "spacing": "Small",

        }



        color = _status_color(status)



        if color != "Default":

            bullet["color"] = color



        result.append(bullet)



    return result





def _render_callout_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    title = _safe_text(block.get("title"))
    text = _safe_text(block.get("text") or block.get("value") or block.get("content"))

    if title:
        heading = _section_heading(title)
        if heading:
            result.append(heading)

    if not text:
        return result

    text_block: dict[str, Any] = {
        "type": "TextBlock",
        "text": text,
        "wrap": True,
        "spacing": "Small" if title else "Medium",
    }
    if block.get("bold") is True:
        text_block["weight"] = "Bolder"

    color = _status_color(block.get("status"))
    if color != "Default":
        text_block["color"] = color

    result.append(text_block)
    return result


def _render_numbered_list_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    title = _safe_text(block.get("title"))
    if title:
        heading = _section_heading(title)
        if heading:
            result.append(heading)

    for index, item in enumerate(_safe_list(block.get("items")), start=1):
        if isinstance(item, dict):
            text = _safe_text(item.get("text") or item.get("title") or item.get("value") or item.get("description"))
            status = item.get("status")
            order_value = item.get("order")
            try:
                order = int(order_value) if order_value is not None else index
            except (TypeError, ValueError):
                order = index
        else:
            text = _safe_text(item)
            status = None
            order = index

        if not text:
            continue

        numbered: dict[str, Any] = {
            "type": "TextBlock",
            "text": f"{order}. {text}",
            "wrap": True,
            "spacing": "Small",
        }
        color = _status_color(status)
        if color != "Default":
            numbered["color"] = color
        result.append(numbered)
    return result


def _render_divider_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    return [{
        "type": "Container",
        "separator": True,
        "spacing": _safe_text(block.get("spacing"), "Medium"),
        "items": [],
    }]


def _render_table_block(

    block: dict[str, Any],

) -> list[dict[str, Any]]:

    """

    Render a generic table using ColumnSet rows.



    We intentionally do not depend on Adaptive Card Table elements,

    because ColumnSet has broader Teams compatibility.

    """



    result: list[dict[str, Any]] = []



    title = _safe_text(block.get("title"))



    if title:

        heading = _section_heading(title)



        if heading:

            result.append(heading)



    columns = [

        column

        for column in _safe_list(block.get("columns"))

        if isinstance(column, dict)

    ]



    rows = _safe_list(block.get("rows"))



    if not columns or not rows:

        return result



    # Prevent giant/unreadable cards.

    # Extra columns are ignored safely.

    columns = columns[:5]



    header_columns: list[dict[str, Any]] = []



    for column in columns:

        label = _safe_text(

            column.get("label")

            or column.get("title")

            or column.get("key"),

            "-",

        )



        header_columns.append(

            {

                "type": "Column",

                "width": "stretch",

                "items": [

                    {

                        "type": "TextBlock",

                        "text": label.upper(),

                        "weight": "Bolder",

                        "size": "Small",

                        "wrap": True,

                    }

                ],

            }

        )



    result.append(

        {

            "type": "ColumnSet",

            "spacing": "Small",

            "columns": header_columns,

        }

    )



    for row in rows:

        if isinstance(row, dict):

            row_values = []



            for column in columns:

                key = _safe_text(column.get("key"))



                row_values.append(

                    _safe_text(

                        row.get(key),

                        "-",

                    )

                )



        elif isinstance(row, list):

            row_values = [

                _safe_text(value, "-")

                for value in row[: len(columns)]

            ]



            while len(row_values) < len(columns):

                row_values.append("-")



        else:

            continue



        row_columns: list[dict[str, Any]] = []



        for value in row_values:

            row_columns.append(

                {

                    "type": "Column",

                    "width": "stretch",

                    "items": [

                        {

                            "type": "TextBlock",

                            "text": value,

                            "size": "Small",

                            "wrap": True,

                        }

                    ],

                }

            )



        result.append(

            {

                "type": "ColumnSet",

                "spacing": "Small",

                "separator": True,

                "columns": row_columns,

            }

        )



    return result





def _render_action_list_block(

    block: dict[str, Any],

) -> list[dict[str, Any]]:

    """

    action_list means a DISPLAY list of recommended actions.



    It does NOT create clickable Adaptive Card buttons.

    """



    result: list[dict[str, Any]] = []



    title = _safe_text(

        block.get("title"),

        "Action Plan",

    )



    heading = _section_heading(title)



    if heading:

        result.append(heading)



    items = _safe_list(block.get("items"))



    for index, item in enumerate(items):

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



            # Legacy compatibility:

            # string-valued "step" can be action text.

            if (

                not action_title

                and isinstance(item.get("step"), str)

            ):

                action_title = _safe_text(

                    item.get("step")

                )



            owner = _safe_text(item.get("owner"))

            status = _safe_text(item.get("status"))



            order_value = (

                item.get("order")

                if item.get("order") is not None

                else item.get("step")

            )



            if isinstance(order_value, (int, float)):

                order = int(order_value)

            else:

                order = index + 1



        else:

            continue



        if not action_title:

            continue



        action_text: dict[str, Any] = {

            "type": "TextBlock",

            "text": f"{order}. {action_title}",

            "weight": "Bolder",

            "wrap": True,

            "spacing": (

                "Small"

                if index == 0

                else "Medium"

            ),

        }



        color = _status_color(status)



        if color != "Default":

            action_text["color"] = color



        result.append(action_text)



        metadata: list[str] = []



        if owner:

            metadata.append(f"Owner · {owner}")



        if status:

            metadata.append(f"Status · {status}")



        if metadata:

            result.append(

                {

                    "type": "TextBlock",

                    "text": "   ·   ".join(metadata),

                    "wrap": True,

                    "isSubtle": True,

                    "size": "Small",

                    "spacing": "None",

                }

            )



    return result





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



    return rendered





# ============================================================

# GENERIC V2 VIEW

# ============================================================





def _build_generic_view_card(

    view: Any,

    title: str,

    subtitle: str = "",

    empty_message: str = "No additional information is available.",

) -> dict[str, Any]:



    view = _safe_dict(view)



    body: list[dict[str, Any]] = [

        {

            "type": "TextBlock",

            "text": title,

            "weight": "Bolder",

            "size": "Medium",

            "wrap": True,

        }

    ]



    if subtitle:

        body.append(

            {

                "type": "TextBlock",

                "text": subtitle,

                "isSubtle": True,

                "wrap": True,

                "spacing": "None",

            }

        )



    rendered_blocks = _render_blocks(

        view.get("blocks")

    )



    if rendered_blocks:

        body.extend(rendered_blocks)

    else:

        body.append(

            {

                "type": "TextBlock",

                "text": empty_message,

                "wrap": True,

                "isSubtle": True,

                "spacing": "Medium",

            }

        )



    return {

        "type": "AdaptiveCard",

        "body": body,

    }





# ============================================================

# V1 LEGACY HELPERS

# ============================================================





def _build_fact_set(

    facts: Any,

) -> dict[str, Any] | None:



    if not isinstance(facts, list) or not facts:

        return None



    normalized_facts = []



    for fact in facts:

        if not isinstance(fact, dict):

            continue



        normalized_facts.append(

            {

                "title": _safe_text(

                    fact.get("label"),

                    "-",

                ),

                "value": _safe_text(

                    fact.get("value"),

                    "-",

                ),

            }

        )



    if not normalized_facts:

        return None



    return {

        "type": "FactSet",

        "facts": normalized_facts,

    }





def _build_bullet_group(

    group: Any,

) -> dict[str, Any] | None:



    if not isinstance(group, dict):

        return None



    items: list[dict[str, Any]] = []



    heading = _safe_text(

        group.get("heading")

    )



    if heading:

        items.append(

            {

                "type": "TextBlock",

                "text": heading.upper(),

                "weight": "Bolder",

                "size": "Small",

                "spacing": "Medium",

            }

        )



    bullets = _safe_list(

        group.get("bullets")

    )



    for bullet in bullets:

        text = _safe_text(bullet)



        if not text:

            continue



        items.append(

            {

                "type": "TextBlock",

                "text": f"• {text}",

                "wrap": True,

                "spacing": "Small",

            }

        )



    if not items:

        return None



    return {

        "type": "Container",

        "items": items,

    }





def _build_details_card_v1(

    details: Any,

) -> dict[str, Any]:



    details = _safe_dict(details)



    body: list[dict[str, Any]] = [

        {

            "type": "TextBlock",

            "text": "Risk Details",

            "weight": "Bolder",

            "size": "Medium",

        },

        {

            "type": "TextBlock",

            "text": (

                "Complete context and exposure information"

            ),

            "isSubtle": True,

            "wrap": True,

            "spacing": "None",

        },

    ]



    facts = _safe_list(

        details.get("facts")

    )



    groups = _safe_list(

        details.get("groups")

    )



    canonical_items = _safe_list(

        details.get("items")

    )



    if not facts:

        facts = canonical_items



    canonical_impact = _safe_list(

        details.get("impact")

    )



    if not groups and canonical_impact:

        groups = [

            {

                "heading": "Impact",

                "bullets": canonical_impact,

            }

        ]



    if facts:

        heading = _section_heading("Overview")



        if heading:

            body.append(heading)



        fact_set = _build_fact_set(facts)



        if fact_set:

            body.append(fact_set)



    for group in groups:

        bullet_group = _build_bullet_group(

            group

        )



        if bullet_group:

            body.append(bullet_group)



    if not facts and not groups:

        body.append(

            {

                "type": "TextBlock",

                "text": (

                    "No additional risk details are available."

                ),

                "wrap": True,

                "isSubtle": True,

                "spacing": "Medium",

            }

        )



    return {

        "type": "AdaptiveCard",

        "body": body,

    }





def _normalize_mitigation_steps(

    steps: Any,

) -> list[dict[str, str]]:



    normalized: list[dict[str, str]] = []



    for item in _safe_list(steps):



        if isinstance(item, str):

            text = _safe_text(item)



            if text:

                normalized.append(

                    {

                        "step": text,

                        "owner": "",

                    }

                )



            continue



        if not isinstance(item, dict):

            continue



        text = ""



        for field in (

            "description",

            "title",

            "action",

            "text",

        ):

            candidate = _safe_text(

                item.get(field)

            )



            if candidate:

                text = candidate

                break



        # Numeric step = ordering metadata.

        # String step = legacy action text.

        if (

            not text

            and isinstance(item.get("step"), str)

        ):

            text = _safe_text(

                item.get("step")

            )



        if not text:

            continue



        normalized.append(

            {

                "step": text,

                "owner": _safe_text(

                    item.get("owner")

                ),

            }

        )



    return normalized





def _build_mitigation_card_v1(

    mitigation: Any,

) -> dict[str, Any]:



    mitigation = _safe_dict(mitigation)



    summary = _safe_text(

        mitigation.get("summary")

    )



    next_action = _safe_text(

        mitigation.get("next_action")

    )



    last_updated = _safe_text(

        mitigation.get("last_updated")

    )



    steps = _normalize_mitigation_steps(

        mitigation.get("steps")

    )



    body: list[dict[str, Any]] = [

        {

            "type": "TextBlock",

            "text": "Mitigation Plan",

            "weight": "Bolder",

            "size": "Medium",

        },

        {

            "type": "TextBlock",

            "text": "Recommended actions to reduce risk",

            "isSubtle": True,

            "wrap": True,

            "spacing": "None",

        },

    ]



    if (

        not summary

        and not steps

        and not next_action

    ):

        body.append(

            {

                "type": "TextBlock",

                "text": (

                    "No mitigation plan is currently available."

                ),

                "wrap": True,

                "isSubtle": True,

                "spacing": "Medium",

            }

        )



        return {

            "type": "AdaptiveCard",

            "body": body,

        }



    if summary:

        heading = _section_heading(

            "Plan Summary"

        )



        if heading:

            body.append(heading)



        body.append(

            {

                "type": "TextBlock",

                "text": summary,

                "wrap": True,

                "spacing": "Small",

            }

        )



    if steps:

        heading = _section_heading(

            "Action Plan"

        )



        if heading:

            body.append(heading)



        for index, item in enumerate(steps):

            body.append(

                {

                    "type": "TextBlock",

                    "text": (

                        f"{index + 1}. "

                        f"{item['step']}"

                    ),

                    "wrap": True,

                    "weight": "Bolder",

                    "spacing": (

                        "Small"

                        if index == 0

                        else "Medium"

                    ),

                }

            )



            owner = _safe_text(

                item.get("owner")

            )



            if owner:

                body.append(

                    {

                        "type": "TextBlock",

                        "text": f"Owner · {owner}",

                        "wrap": True,

                        "isSubtle": True,

                        "size": "Small",

                        "spacing": "None",

                    }

                )



    if next_action:

        heading = _section_heading(

            "Next Action"

        )



        if heading:

            body.append(heading)



        body.append(

            {

                "type": "TextBlock",

                "text": next_action,

                "wrap": True,

                "spacing": "Small",

            }

        )



    if last_updated:

        body.append(

            {

                "type": "TextBlock",

                "text": (

                    f"Last updated · {last_updated}"

                ),

                "wrap": True,

                "isSubtle": True,

                "size": "Small",

                "spacing": "Medium",

            }

        )



    return {

        "type": "AdaptiveCard",

        "body": body,

    }





# ============================================================

# SHARED HEADER / FOOTER

# ============================================================





def _build_header(

    sender: dict[str, Any],

) -> dict[str, Any]:



    sender_name = _safe_text(

        sender.get("source")

        or sender.get("name"),

        "StratSync RRM",

    )



    sender_time = _safe_text(

        sender.get("time")

        or sender.get("timestamp")

    )



    columns: list[dict[str, Any]] = [

        {

            "type": "Column",

            "width": "stretch",

            "items": [

                {

                    "type": "TextBlock",

                    "text": sender_name,

                    "weight": "Bolder",

                    "size": "Small",

                    "color": "Accent",

                    "wrap": True,

                }

            ],

        }

    ]



    if sender_time:

        columns.append(

            {

                "type": "Column",

                "width": "auto",

                "items": [

                    {

                        "type": "TextBlock",

                        "text": sender_time,

                        "size": "Small",

                        "isSubtle": True,

                        "horizontalAlignment": "Right",

                        "wrap": True,

                    }

                ],

            }

        )



    return {

        "type": "ColumnSet",

        "columns": columns,

    }





def _build_title_row(

    title: str,

    severity: str,

) -> dict[str, Any]:



    columns: list[dict[str, Any]] = [

        {

            "type": "Column",

            "width": "stretch",

            "items": [

                {

                    "type": "TextBlock",

                    "text": title,

                    "weight": "Bolder",

                    "size": "Medium",

                    "wrap": True,

                }

            ],

        }

    ]



    if severity:

        columns.append(

            {

                "type": "Column",

                "width": "auto",

                "items": [

                    {

                        "type": "TextBlock",

                        "text": severity.upper(),

                        "weight": "Bolder",

                        "size": "Small",

                        "color": _severity_color(

                            severity

                        ),

                        "horizontalAlignment": "Right",

                        "wrap": True,

                    }

                ],

            }

        )



    return {

        "type": "ColumnSet",

        "spacing": "Medium",

        "columns": columns,

    }





def _build_footer(

    risk: dict[str, Any],

    sender: dict[str, Any],

) -> dict[str, Any]:



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



    footer_text = source



    if risk_id:

        footer_text += f" · Risk ID {risk_id}"



    items: list[dict[str, Any]] = [

        {

            "type": "TextBlock",

            "text": footer_text,

            "size": "Small",

            "isSubtle": True,

            "wrap": True,

        }

    ]



    if timestamp:

        items.append(

            {

                "type": "TextBlock",

                "text": timestamp,

                "size": "Small",

                "isSubtle": True,

                "wrap": True,

                "spacing": "None",

            }

        )



    return {

        "type": "Container",

        "spacing": "Medium",

        "separator": True,

        "items": items,

    }





# ============================================================

# SCHEMA V2

# ============================================================





def _is_schema_v2(

    risk: dict[str, Any],

) -> bool:



    version = risk.get("schema_version")



    try:

        version_number = int(version)

    except (TypeError, ValueError):

        version_number = 1



    return (

        version_number >= 2

        and isinstance(risk.get("views"), dict)

    )





def _build_v2_card(

    risk: dict[str, Any],

) -> dict[str, Any]:



    sender = _safe_dict(

        risk.get("sender")

    )



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



    card_body: list[dict[str, Any]] = [

        _build_header(sender),

        _build_title_row(

            title,

            severity,

        ),

    ]



    if subtitle:

        card_body.append(

            {

                "type": "TextBlock",

                "text": subtitle,

                "isSubtle": True,

                "wrap": True,

                "spacing": "None",

            }

        )



    if summary:

        card_body.append(

            {

                "type": "TextBlock",

                "text": summary,

                "wrap": True,

                "spacing": "Medium",

            }

        )



    # Generic main notification content.

    card_body.extend(

        _render_blocks(

            notification_view.get("blocks")

        )

    )



    card_body.append(

        _build_footer(

            risk,

            sender,

        )

    )



    actions: list[dict[str, Any]] = []



    # Details button only appears when the view exists

    # and contains blocks.

    if _safe_list(

        details_view.get("blocks")

    ):

        details_card = _build_generic_view_card(

            details_view,

            title=_safe_text(

                details_view.get("title"),

                "Risk Details",

            ),

            subtitle=_safe_text(

                details_view.get("subtitle"),

                "Complete context and exposure information",

            ),

            empty_message=(

                "No additional risk details are available."

            ),

        )



        actions.append(

            {

                "type": "Action.ShowCard",

                "title": _safe_text(

                    details_view.get("action_label"),

                    "View Details",

                ),

                "card": details_card,

            }

        )



    # Mitigation button only appears when the view exists

    # and contains blocks.

    if _safe_list(

        mitigation_view.get("blocks")

    ):

        mitigation_card = _build_generic_view_card(

            mitigation_view,

            title=_safe_text(

                mitigation_view.get("title"),

                "Mitigation Plan",

            ),

            subtitle=_safe_text(

                mitigation_view.get("subtitle"),

                "Recommended actions to reduce risk",

            ),

            empty_message=(

                "No mitigation plan is currently available."

            ),

        )



        actions.append(

            {

                "type": "Action.ShowCard",

                "title": _safe_text(

                    mitigation_view.get(

                        "action_label"

                    ),

                    "Mitigation Plan",

                ),

                "card": mitigation_card,

            }

        )



    adaptive_card: dict[str, Any] = {

        "type": "AdaptiveCard",

        "$schema": (

            "http://adaptivecards.io/"

            "schemas/adaptive-card.json"

        ),

        "version": "1.5",

        "msteams": {

            "width": "Full",

        },

        "body": card_body,

    }



    if actions:

        adaptive_card["actions"] = actions



    return adaptive_card





# ============================================================

# SCHEMA V1

# ============================================================





def _build_v1_card(

    risk: dict[str, Any],

) -> dict[str, Any]:



    sender = _safe_dict(

        risk.get("sender")

    )



    alert = _safe_dict(

        risk.get("alert")

    )



    title = _safe_text(

        alert.get("title")

        or risk.get("title"),

        "Risk Alert",

    )



    severity = _safe_text(

        alert.get("severity")

        or risk.get("severity_label")

        or risk.get("severity"),

        "Unknown",

    )



    subtitle = _safe_text(

        alert.get("subtitle")

        or risk.get("subtitle")

    )



    summary = _safe_text(

        alert.get("summary")

        or risk.get("summary")

    )



    card_body: list[dict[str, Any]] = [

        _build_header(sender),

        _build_title_row(

            title,

            severity,

        ),

    ]



    if subtitle:

        card_body.append(

            {

                "type": "TextBlock",

                "text": subtitle,

                "isSubtle": True,

                "wrap": True,

                "spacing": "None",

            }

        )



    if summary:

        card_body.append(

            {

                "type": "TextBlock",

                "text": summary,

                "wrap": True,

                "spacing": "Medium",

            }

        )



    # Preserve V1 metrics.

    metrics = [

        metric

        for metric in _safe_list(

            risk.get("metrics")

        )

        if isinstance(metric, dict)

    ]



    if metrics:

        card_body.extend(

            _render_metrics_block(

                {

                    "type": "metrics",

                    "title": "Key Metrics",

                    "items": metrics,

                    "columns": 2,

                }

            )

        )



    card_body.append(

        _build_footer(

            risk,

            sender,

        )

    )



    details_card = _build_details_card_v1(

        risk.get("details")

    )



    mitigation_card = _build_mitigation_card_v1(

        risk.get("mitigation")

    )



    actions = [

        {

            "type": "Action.ShowCard",

            "title": "View Details",

            "card": details_card,

        },

        {

            "type": "Action.ShowCard",

            "title": "Mitigation Plan",

            "card": mitigation_card,

        },

    ]



    return {

        "type": "AdaptiveCard",

        "$schema": (

            "http://adaptivecards.io/"

            "schemas/adaptive-card.json"

        ),

        "version": "1.5",

        "msteams": {

            "width": "Full",

        },

        "body": card_body,

        "actions": actions,

    }





# ============================================================

# PUBLIC API

# ============================================================





def build_teams_notification_payload(

    risk: dict[str, Any],

) -> dict[str, Any]:

    """

    Convert a risk document into a Microsoft Teams

    Adaptive Card webhook envelope.



    Supported schemas:



        V1:

            Existing StratSync risk structure.



        V2:

            Generic block-based structure using:



                views.notification.blocks

                views.details.blocks

                views.mitigation.blocks



    Supported V2 block types:



        text

        key_value

        metrics

        bullet_list

        table

        action_list



    This function only renders the payload.

    It does not send the webhook.

    """



    risk = _safe_dict(risk)



    if _is_schema_v2(risk):

        adaptive_card = _build_v2_card(

            risk

        )

    else:

        adaptive_card = _build_v1_card(

            risk

        )



    return {

        "type": "message",

        "attachments": [

            {

                "contentType": (

                    "application/vnd.microsoft.card.adaptive"

                ),

                "content": adaptive_card,

            }

        ],

    }







