from app.services.teams_card_renderer import (
    _render_generic_block,
    build_teams_notification_payload,
)
from app.services.slack_block_renderer import (
    build_slack_notification_payload,
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


def test_associated_risks_render_as_ids_in_teams_v1_and_v2():
    for risk in [
        {
            "title": "V1 Risk",
            "severity": "high",
            "associated_risk_ids": [
                " RSK-AAAA-1111 ",
                "",
                {"risk_id": "RSK-SHOULD-NOT-RENDER"},
                "RSK-BBBB-2222",
            ],
        },
        {
            "schema_version": 2,
            "title": "V2 Risk",
            "severity_label": "High",
            "views": {"notification": {"blocks": []}},
            "associated_risk_ids": [
                "RSK-AAAA-1111",
                "RSK-BBBB-2222",
            ],
        },
    ]:
        card = build_teams_notification_payload(risk)["attachments"][0][
            "content"
        ]
        rendered = [element.get("text", "") for element in card["body"]]

        assert "ASSOCIATED RISKS" in rendered
        assert "• RSK-AAAA-1111" in rendered
        assert "• RSK-BBBB-2222" in rendered
        assert "RSK-SHOULD-NOT-RENDER" not in str(card)


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
        assert "ASSOCIATED RISKS" not in str(teams_card)

        slack_payload = build_slack_notification_payload(risk)
        assert "ASSOCIATED RISKS" not in str(slack_payload)


def test_associated_risks_render_as_escaped_ids_in_slack_v1_and_v2():
    for risk in [
        {
            "title": "V1 Risk",
            "severity": "high",
            "associated_risk_ids": ["RSK-<AAAA>-1111"],
        },
        {
            "schema_version": 2,
            "title": "V2 Risk",
            "severity_label": "High",
            "views": {"notification": {"blocks": []}},
            "associated_risk_ids": ["RSK-<AAAA>-1111"],
        },
    ]:
        payload = build_slack_notification_payload(risk)
        assert "*ASSOCIATED RISKS*" in str(payload)
        assert "RSK-&lt;AAAA&gt;-1111" in str(payload)
