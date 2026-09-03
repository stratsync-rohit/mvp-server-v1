from copy import deepcopy


def normalize_mitigation_plan_for_notification(risk: dict) -> dict:
    """Return an n8n-safe risk copy without changing the Risk API schema."""
    normalized_risk = deepcopy(risk)
    mitigation = normalized_risk.get("mitigation")

    if not isinstance(mitigation, dict):
        return normalized_risk

    steps = mitigation.get("steps")
    if not isinstance(steps, list):
        return normalized_risk

    normalized_steps = []
    for item in steps:
        if isinstance(item, str):
            step_text = item.strip()
            if step_text:
                normalized_steps.append({"step": step_text, "owner": "-"})
            continue

        if not isinstance(item, dict):
            continue

        step_text = item.get("step")
        if not isinstance(step_text, str) or not step_text.strip():
            continue

        normalized_item = deepcopy(item)
        normalized_item["step"] = step_text.strip()

        owner = item.get("owner")
        normalized_item["owner"] = (
            owner.strip()
            if isinstance(owner, str) and owner.strip()
            else "-"
        )
        normalized_steps.append(normalized_item)

    mitigation["steps"] = normalized_steps
    return normalized_risk
