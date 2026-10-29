import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import app.services.teams_card_renderer as teams_card_renderer

from app.services.teams_card_renderer import (
    _render_generic_block,
    _render_metrics_block,
    _group_metrics,
    build_teams_notification_payload,
)
from app.services.slack_block_renderer import (
    build_slack_notification_payload,
)
from app.services.connected_risk_overview import (
    build_connected_risk_overview_rows,
)
from app.utils.risk_time import calculate_elapsed_time


def _timing_summary_row(card):
    return next(
        element
        for element in card["body"]
        if element.get("type") == "ColumnSet"
        and [
            column["items"][0].get("text")
            for column in element.get("columns", [])
            if column.get("items")
        ]
        == ["REPORTED DATE", "ELAPSED TIME"]
    )


def _timing_summary_values(card):
    row = _timing_summary_row(card)
    return [column["items"][1]["text"] for column in row["columns"]]


def test_timing_summary_formats_reported_date_and_recalculates_elapsed_time():
    reported_date = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)
    risk = {
        "title": "Supplier delivery disruption",
        "severity": "critical",
        "summary": "A supplier has missed its delivery commitment.",
        "reported_date": reported_date,
    }

    card = build_teams_notification_payload(risk)["attachments"][0][
        "content"
    ]

    assert _timing_summary_values(card) == [
        "22 Oct 2026, 6:00 PM IST",
        calculate_elapsed_time(reported_date),
    ]
    assert [
        element["type"] for element in card["body"][:4]
    ] == ["ColumnSet", "ColumnSet", "ColumnSet", "TextBlock"]


def test_timing_summary_accepts_serialized_utc_dates_and_does_not_mutate_risk():
    reported_date = datetime.now(timezone.utc) - timedelta(hours=27)
    risk = {
        "schema_version": 2,
        "title": "Inventory risk",
        "severity_label": "High",
        "reported_date": reported_date.isoformat().replace("+00:00", "Z"),
        "views": {"notification": {"blocks": []}},
    }
    original_risk = deepcopy(risk)

    card = build_teams_notification_payload(risk)["attachments"][0][
        "content"
    ]

    assert _timing_summary_values(card)[0].endswith("IST")
    assert _timing_summary_values(card)[1] == "1 day 3 hours"
    assert risk == original_risk


def test_timing_summary_uses_fallbacks_once_when_reported_date_is_missing():
    risk = {
        "title": "Legacy risk",
        "severity": "high",
        "summary": "Existing risk without a reported date.",
        "sender": {"timestamp": "09:42 AM IST"},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    card = build_teams_notification_payload(risk)["attachments"][0][
        "content"
    ]

    assert _timing_summary_values(card) == ["Not specified", "Not available"]
    rendered_card = str(card)
    assert rendered_card.count("REPORTED DATE") == 1
    assert rendered_card.count("ELAPSED TIME") == 1


def test_timing_summary_preserves_existing_v1_actions():
    card = build_teams_notification_payload(
        {
            "title": "Actionable risk",
            "severity": "high",
            "reported_date": datetime.now(timezone.utc),
            "summary": "Summary remains below the timing summary.",
            "details": {"section_title": "DETAILS"},
            "mitigation": {
                "summary": "Mitigation summary",
                "steps": [],
            },
        }
    )["attachments"][0]["content"]

    assert [action["title"] for action in card["actions"]] == [
        "View Details",
        "Mitigation Plan",
    ]
    assert card["body"][3]["text"] == (
        "Summary remains below the timing summary."
    )


def test_generic_v2_dispatcher_supports_all_block_types():
    blocks = [
        {"type": "text", "text": "Text"},
        {"type": "callout", "text": "Callout"},
        {
            "type": "metrics",
            "items": [{"label": "Exposure", "value": "$184,500"}],
        },
        {
            "type": "key_value",
            "items": [{"label": "Owner", "value": "Finance"}],
        },
        {"type": "bullet_list", "items": ["First"]},
        {"type": "numbered_list", "items": ["First"]},
        {
            "type": "table",
            "columns": [{"key": "name", "label": "Name"}],
            "rows": [{"name": "First"}],
        },
        {"type": "action_list", "items": ["First"]},
        {"type": "divider"},
    ]

    for block in blocks:
        assert _render_generic_block(block), block["type"]


def test_metrics_automatically_use_compact_balanced_rows():
    cases = [
        (1, [1]),
        (2, [2]),
        (3, [3]),
        (4, [4]),
        (5, [3, 2]),
        (6, [3, 3]),
        (7, [4, 3]),
    ]
    metric_templates = [
        ("Estimated Repair Cost", "US$45,000"),
        ("Expected Maintenance Downtime", "72 hours"),
        ("Vessel Readiness Score", "9/10"),
        ("Uptime", "1 sec"),
        (
            "Estimated Operational Financial Exposure",
            "US$1,250,000.75",
        ),
        ("Deadline", "2026-10-20 23:59 UTC"),
        ("Seventh Metric", "Value 7"),
    ]

    for metric_count, expected_row_sizes in cases:
        metrics = [
            {
                "label": label,
                "value": value,
            }
            for label, value in metric_templates[:metric_count]
        ]
        rendered = _render_metrics_block(
            {
                "type": "metrics",
                "title": "Risk metrics",
                "items": metrics,
            }
        )

        assert rendered[0]["text"] == "RISK METRICS"
        rows = rendered[1:]
        assert [len(row["columns"]) for row in rows] == expected_row_sizes
        assert [
            column["items"][0]["items"][-1]["text"]
            for row in rows
            for column in row["columns"]
        ] == [value for _, value in metric_templates[:metric_count]]
        assert [
            column["items"][0]["items"][0]["text"]
            for row in rows
            for column in row["columns"]
        ] == [label.upper() for label, _ in metric_templates[:metric_count]]

        for row in rows:
            assert row["type"] == "ColumnSet"
            for column in row["columns"]:
                assert column["width"] == "stretch"
                container = column["items"][0]
                assert container["type"] == "Container"
                assert container["style"] == "emphasis"
                assert container["items"][0]["wrap"] is True
                assert container["items"][0]["spacing"] == "None"
                assert container["items"][1]["wrap"] is True
                assert container["items"][1]["spacing"] == "Small"


def test_metrics_respect_valid_explicit_columns_and_fall_back_safely():
    items = [
        {"label": f"Metric {index}", "value": index}
        for index in range(1, 7)
    ]

    assert [len(group) for group in _group_metrics(items, 1)] == [1] * 6
    assert [len(group) for group in _group_metrics(items, "2")] == [2, 2, 2]
    assert [len(group) for group in _group_metrics(items, 4)] == [4, 2]
    assert [len(group) for group in _group_metrics(items + items[:4])] == [4, 3, 3]

    for invalid_columns in (0, -1, 5, "not-a-number", 2.5, True):
        assert [len(group) for group in _group_metrics(items[:4], invalid_columns)] == [4]

    rendered = _render_metrics_block(
        {"type": "metrics", "columns": 2, "items": items}
    )
    assert [len(row["columns"]) for row in rendered[1:]] == [2, 2, 2]
    assert [
        column["items"][0]["items"][-1]["text"]
        for row in rendered[1:]
        for column in row["columns"]
    ] == [str(index) for index in range(1, 7)]


def test_metrics_preserve_status_colors_special_characters_and_safe_values():
    rendered = _render_metrics_block(
        {
            "type": "metrics",
            "items": [
                {
                    "label": "Critical <&>",
                    "value": "$1,000 & rising",
                    "status": "critical",
                },
                {
                    "label": "Warning / pending",
                    "value": "50%",
                    "status": "warning",
                },
                {"label": "Healthy", "value": "✓", "status": "healthy"},
                {"label": "Information", "value": "R&D", "status": "info"},
            ],
        }
    )

    metric_values = [
        column["items"][0]["items"][-1]
        for row in rendered[1:]
        for column in row["columns"]
    ]
    assert [item["text"] for item in metric_values] == [
        "$1,000 & rising",
        "50%",
        "✓",
        "R&D",
    ]
    assert [item["color"] for item in metric_values] == [
        "Attention",
        "Warning",
        "Good",
        "Accent",
    ]
    card = build_teams_notification_payload(
        {
            "schema_version": 2,
            "views": {
                "notification": {
                    "blocks": [
                        {
                            "type": "metrics",
                            "items": [
                                {
                                    "label": "Critical <&>",
                                    "value": "$1,000 & rising",
                                    "status": "critical",
                                }
                            ],
                        }
                    ]
                }
            },
        }
    )["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert any(
        column["items"][0].get("style") == "emphasis"
        for row in card["body"]
        if row.get("type") == "ColumnSet"
        for column in row["columns"]
    )
    assert json.loads(json.dumps(card)) == card


def test_metrics_ignore_malformed_items_and_handle_missing_labels_and_values():
    rendered = _render_metrics_block(
        {
            "type": "metrics",
            "items": [
                None,
                "not a metric",
                {"value": "42"},
                {"label": "", "value": ""},
                {"label": "Unavailable", "value": None},
            ],
        }
    )

    columns = [
        column
        for row in rendered[1:]
        for column in row["columns"]
    ]
    assert len(columns) == 3
    assert columns[0]["items"][0]["items"] == [
        {
            "type": "TextBlock",
            "text": "42",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Default",
            "wrap": True,
            "spacing": "None",
        }
    ]
    assert columns[1]["items"][0]["items"][-1]["text"] == "-"
    assert columns[2]["items"][0]["items"][-1]["text"] == "-"
    assert columns[2]["items"][0]["items"][0]["text"] == "UNAVAILABLE"


def test_generic_v2_callout_is_a_direct_text_block_in_order():
    callout_text = "$184,500 revenue currently exposed"
    risk = {
        "schema_version": 2,
        "title": "Revenue Risk",
        "severity_label": "Critical",
        "subtitle": "Subtitle",
        "summary": "Summary",
        "views": {
            "notification": {
                "blocks": [
                    {
                        "type": "callout",
                        "text": callout_text,
                        "status": "critical",
                        "bold": True,
                    },
                    {"type": "divider"},
                    {
                        "type": "key_value",
                        "items": [{"label": "Owner", "value": "Finance"}],
                    },
                ],
            }
        },
    }

    card = build_teams_notification_payload(risk)["attachments"][0]["content"]
    body = card["body"]
    callout_index = next(
        index
        for index, element in enumerate(body)
        if element.get("text") == callout_text
    )

    assert body[callout_index] == {
        "type": "TextBlock",
        "text": callout_text,
        "wrap": True,
        "spacing": "Medium",
        "weight": "Bolder",
        "color": "Attention",
    }
    assert body[callout_index + 1]["type"] == "Container"
    assert body[callout_index + 1]["separator"] is True
    assert body[callout_index + 2]["type"] == "FactSet"
    assert body[callout_index + 2]["facts"] == [
        {"title": "Owner", "value": "Finance"}
    ]
    assert card["msteams"] == {"width": "Full"}


def test_connected_risk_overview_renders_one_and_multiple_rows_in_teams():
    for risk in [
        {
            "title": "V1 Risk",
            "severity": "high",
            "connected_risk_overview": [
                {
                    "risk_id": "RSK-AAAA-1111",
                    "risk": "Supplier Delivery Disruption",
                    "severity": "Critical",
                    "primary_exposure": "7-day shipment delay",
                },
                {
                    "risk_id": "RSK-BBBB-2222",
                    "risk": "Capacity Constraint",
                    "severity": "High",
                    "primary_exposure": "2-week backlog",
                },
            ],
        },
        {
            "schema_version": 2,
            "title": "V2 Risk",
            "severity_label": "High",
            "views": {"notification": {"blocks": []}},
            "connected_risk_overview": [
                {
                    "risk_id": "RSK-AAAA-1111",
                    "risk": "Supplier Delivery Disruption",
                    "severity": "Critical",
                    "primary_exposure": "7-day shipment delay",
                },
            ],
        },
    ]:
        card = build_teams_notification_payload(risk)["attachments"][0][
            "content"
        ]
        rendered = str(card)

        assert "CONNECTED RISK OVERVIEW" in rendered
        assert "RISK ID" in rendered
        assert "RISK" in rendered
        assert "SEVERITY" in rendered
        assert "PRIMARY EXPOSURE" in rendered
        assert "RSK-AAAA-1111" in rendered
        assert "Supplier Delivery Disruption" in rendered
        if risk["title"] == "V1 Risk":
            assert "RSK-BBBB-2222" in rendered
            assert "Capacity Constraint" in rendered


def test_teams_connected_risk_overview_uses_generic_table_renderer(
    monkeypatch,
):
    risk = {
        "title": "Current Risk",
        "severity": "high",
        "connected_risk_overview": [
            {
                "risk_id": "RSK-STCK-7314",
                "risk": "WAREHOUSE INVENTORY STOCKOUT WITH A VERY LONG TITLE",
                "severity": "High",
                "primary_exposure": None,
            },
            {
                "risk_id": "RSK-CONT-5840",
                "risk": "END-TO-END SUPPLY CHAIN DISRUPTION",
                "severity": "Critical",
                "primary_exposure": "  ",
            },
        ],
    }

    rendered_table_blocks = []
    render_table_block = teams_card_renderer._render_table_block

    def record_table_block(block):
        rendered_table_blocks.append(block)
        return render_table_block(block)

    monkeypatch.setattr(
        teams_card_renderer,
        "_render_table_block",
        record_table_block,
    )

    card = build_teams_notification_payload(risk)["attachments"][0][
        "content"
    ]
    assert len(rendered_table_blocks) == 1
    assert rendered_table_blocks[0]["type"] == "table"
    assert rendered_table_blocks[0]["title"] == "Connected Risk Overview"
    assert [
        row["primary_exposure"]
        for row in rendered_table_blocks[0]["rows"]
    ] == ["-", "-"]

    body = card["body"]
    heading_index = next(
        index
        for index, element in enumerate(body)
        if element.get("text") == "CONNECTED RISK OVERVIEW"
    )

    header = body[heading_index + 1]
    rows = [body[heading_index + 2], body[heading_index + 3]]

    assert header["type"] == "ColumnSet"
    assert [
        column["items"][0]["text"]
        for column in header["columns"]
    ] == ["RISK ID", "RISK", "SEVERITY", "PRIMARY EXPOSURE"]
    assert all(
        [column["width"] for column in row["columns"]]
        == ["stretch"] * 4
        for row in rows
    )
    assert [
        column["items"][0]["text"]
        for column in rows[0]["columns"]
    ] == [
        "RSK-STCK-7314",
        "WAREHOUSE INVENTORY STOCKOUT WITH A VERY LONG TITLE",
        "High",
        "-",
    ]
    assert [
        column["items"][0]["text"]
        for column in rows[1]["columns"]
    ] == [
        "RSK-CONT-5840",
        "END-TO-END SUPPLY CHAIN DISRUPTION",
        "Critical",
        "-",
    ]
    assert rows[0]["separator"] is True
    assert rows[1]["separator"] is True

    footer_index = next(
        index
        for index, element in enumerate(body)
        if element.get("items")
        and element["items"][0].get("text") == "StratSync RRM"
    )
    assert footer_index > heading_index + 3


def test_connected_risk_overview_rows_apply_mapping_fallbacks_and_filters():
    rows = build_connected_risk_overview_rows(
        [
            "RSK-DIRECT",
            "RSK-REVERSE",
            "RSK-NO-EXPOSURE",
            "RSK-DIRECT",
            "RSK-CURRENT",
        ],
        [
            {
                "risk_id": "RSK-DIRECT",
                "title": "Direct Risk",
                "severity": "medium",
                "metadata": {
                    "primary_exposure": "Primary inventory exposure",
                    "exposure_summary": "Inventory buffer",
                },
            },
            {
                "risk_id": "RSK-REVERSE",
                "title": "Reverse-linked Risk",
                "severity_label": "Critical",
                "summary": "Supplier concentration",
            },
            {
                "risk_id": "RSK-NO-EXPOSURE",
                "title": "No Exposure Risk",
                "severity": "low",
                "summary": "Summary fallback must not render",
            },
            {
                "risk_id": "RSK-NULL-EXPOSURE",
                "title": "Null Exposure Risk",
                "severity": "low",
                "metadata": {"primary_exposure": None},
            },
            {
                "risk_id": "RSK-BLANK-EXPOSURE",
                "title": "Blank Exposure Risk",
                "severity": "low",
                "metadata": {"primary_exposure": "  "},
            },
            {"risk_id": "RSK-CURRENT", "title": "Self"},
        ],
        canonical_risk_id="RSK-CURRENT",
    )

    assert rows == [
        {
            "risk_id": "RSK-DIRECT",
            "risk": "Direct Risk",
            "severity": "Medium",
            "primary_exposure": "Primary inventory exposure",
        },
        {
            "risk_id": "RSK-REVERSE",
            "risk": "Reverse-linked Risk",
            "severity": "Critical",
            "primary_exposure": "-",
        },
        {
            "risk_id": "RSK-NO-EXPOSURE",
            "risk": "No Exposure Risk",
            "severity": "Low",
            "primary_exposure": "-",
        },
        {
            "risk_id": "RSK-NULL-EXPOSURE",
            "risk": "Null Exposure Risk",
            "severity": "Low",
            "primary_exposure": "-",
        },
        {
            "risk_id": "RSK-BLANK-EXPOSURE",
            "risk": "Blank Exposure Risk",
            "severity": "Low",
            "primary_exposure": "-",
        },
    ]


def test_associated_risks_are_omitted_when_missing_or_empty():
    for risk in [
        {"title": "No associations", "severity": "low"},
        {
            "schema_version": 2,
            "views": {"notification": {"blocks": []}},
            "associated_risk_ids": [],
        },
    ]:
        teams_card = build_teams_notification_payload(risk)
        assert "CONNECTED RISK OVERVIEW" not in str(teams_card)

        slack_payload = build_slack_notification_payload(risk)
        assert "CONNECTED RISK OVERVIEW" not in str(slack_payload)


def test_connected_risk_overview_renders_in_slack_v1_and_v2():
    for risk in [
        {
            "title": "V1 Risk",
            "severity": "high",
            "connected_risk_overview": [
                {
                    "risk_id": "RSK-<AAAA>-1111",
                    "risk": "Supplier <risk>",
                    "severity": "High",
                    "primary_exposure": "Shipment delay",
                }
            ],
        },
        {
            "schema_version": 2,
            "title": "V2 Risk",
            "severity_label": "High",
            "views": {"notification": {"blocks": []}},
            "connected_risk_overview": [
                {
                    "risk_id": "RSK-<AAAA>-1111",
                    "risk": "Supplier <risk>",
                    "severity": "High",
                    "primary_exposure": "Shipment delay",
                }
            ],
        },
    ]:
        payload = build_slack_notification_payload(risk)
        assert "*CONNECTED RISK OVERVIEW*" in str(payload)
        assert "Risk ID" in str(payload)
        assert "Primary Exposure" in str(payload)
        assert "RSK-&lt;AAAA&gt;-1111" in str(payload)
        assert "Supplier &lt;risk&gt;" in str(payload)
