import pytest

from app.utils.mitigation_plan import normalize_mitigation_plan_for_notification


def _normalize_steps(steps):
    risk = {
        "mitigation": {
            "summary": "Keep this summary",
            "steps": steps,
            "last_updated": "2026-09-14",
            "next_action": "Keep this next action",
        }
    }

    result = normalize_mitigation_plan_for_notification(risk)

    assert result["mitigation"]["summary"] == "Keep this summary"
    assert result["mitigation"]["last_updated"] == "2026-09-14"
    assert result["mitigation"]["next_action"] == "Keep this next action"
    return result["mitigation"]["steps"]


def test_normalizes_existing_string_steps_and_ignores_blanks():
    assert _normalize_steps([
        " Review inventory ",
        "   ",
        "Confirm purchase orders",
    ]) == [
        {"step": "Review inventory", "owner": "-"},
        {"step": "Confirm purchase orders", "owner": "-"},
    ]


def test_normalizes_existing_object_with_string_step():
    assert _normalize_steps([
        {"step": " Confirm purchase orders ", "owner": " Procurement "}
    ]) == [
        {"step": "Confirm purchase orders", "owner": "Procurement"}
    ]


def test_normalizes_legacy_numeric_steps_using_description():
    assert _normalize_steps([
        {
            "step": 1,
            "title": "monday-test-1",
            "description": "monday-test-1",
            "owner": "Rohit",
        },
        {
            "step": 2,
            "title": "monday-test-1",
            "description": "test-Rohit Choukiker",
            "owner": "Mitigation Plan",
        },
    ]) == [
        {"step": "monday-test-1", "owner": "Rohit"},
        {"step": "test-Rohit Choukiker", "owner": "Mitigation Plan"},
    ]


def test_normalizes_canonical_numeric_steps_using_title_without_description():
    assert _normalize_steps([
        {
            "step": 1,
            "title": "Confirm cover gap",
            "owner": " Procurement ",
        }
    ]) == [
        {"step": "Confirm cover gap", "owner": "Procurement"}
    ]


@pytest.mark.parametrize(
    ("item", "expected_text"),
    [
        (
            {
                "description": " Description ",
                "title": "Title",
                "action": "Action",
                "text": "Text",
                "step": "Step",
            },
            "Description",
        ),
        (
            {
                "description": "   ",
                "title": " Title ",
                "action": "Action",
                "text": "Text",
                "step": "Step",
            },
            "Title",
        ),
        (
            {
                "description": None,
                "title": "",
                "action": " Action ",
                "text": "Text",
                "step": "Step",
            },
            "Action",
        ),
        (
            {
                "description": 7,
                "title": [],
                "action": "\t",
                "text": " Text ",
                "step": "Step",
            },
            "Text",
        ),
        (
            {
                "description": "",
                "title": " ",
                "action": None,
                "text": {},
                "step": " Step fallback ",
            },
            "Step fallback",
        ),
    ],
)
def test_object_action_text_uses_required_precedence(item, expected_text):
    assert _normalize_steps([item]) == [
        {"step": expected_text, "owner": "-"}
    ]


def test_numeric_step_is_ordering_only_and_not_action_text():
    assert _normalize_steps([{"step": 1, "owner": "Rohit"}]) == []


@pytest.mark.parametrize(
    "owner",
    [None, "", "   ", 123, {}, []],
)
def test_malformed_or_blank_owner_uses_fallback(owner):
    assert _normalize_steps([
        {"description": "Take action", "owner": owner}
    ]) == [
        {"step": "Take action", "owner": "-"}
    ]


def test_missing_owner_uses_fallback():
    assert _normalize_steps([{"description": "Take action"}]) == [
        {"step": "Take action", "owner": "-"}
    ]


def test_empty_steps_remain_empty():
    assert _normalize_steps([]) == []


def test_mixed_steps_ignore_malformed_items_without_losing_valid_siblings():
    assert _normalize_steps([
        " String action ",
        {
            "step": 2,
            "description": " Object action ",
            "owner": " Rohit ",
        },
        None,
        {},
        {"step": 3, "title": " Title fallback "},
        42,
        ["nested list"],
        {"step": 4, "description": False},
    ]) == [
        {"step": "String action", "owner": "-"},
        {"step": "Object action", "owner": "Rohit"},
        {"step": "Title fallback", "owner": "-"},
    ]
