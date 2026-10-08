import app.services.teams_card_renderer as teams_card_renderer

from app.services.teams_card_renderer import (
    _render_generic_block,
    build_teams_notification_payload,
)
from app.services.slack_block_renderer import (
    build_slack_notification_payload,
)
from app.services.connected_risk_overview import (
    build_connected_risk_overview_rows,
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
