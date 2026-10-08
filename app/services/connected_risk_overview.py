"""Presentation helpers for notification connected-risk summaries."""

from __future__ import annotations

from typing import Any


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text or fallback


def _format_severity(value: Any) -> str:
    text = _text(value)
    if not text:
        return "—"

    return text.replace("_", " ").replace("-", " ").title()


def _first_text(*values: Any, fallback: str = "—") -> str:
    for value in values:
        text = _text(value)
        if text:
            return text

    return fallback


def _primary_exposure(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return "-"

    value = metadata.get("primary_exposure")
    if not isinstance(value, str):
        return "-"

    value = value.strip()
    return value or "-"


def build_connected_risk_overview_rows(
    resolved_associated_risk_ids: Any,
    associated_risk_documents: Any,
    canonical_risk_id: str | None = None,
) -> list[dict[str, str]]:
    """Build ordered, compact rows from notification-time risk resolution.

    The resolver owns association semantics. This helper only preserves that
    order while joining the resolved IDs to their risk documents and mapping
    fields for presentation.
    """

    if not isinstance(resolved_associated_risk_ids, list):
        return []

    documents_by_id: dict[str, dict[str, Any]] = {}
    documents = (
        associated_risk_documents
        if isinstance(associated_risk_documents, list)
        else []
    )
    for document in documents:
        if not isinstance(document, dict):
            continue

        risk_id = _text(document.get("risk_id"))
        if risk_id and risk_id not in documents_by_id:
            documents_by_id[risk_id] = document

    canonical_id = _text(canonical_risk_id)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for resolved_id in resolved_associated_risk_ids:
        resolved_id = _text(resolved_id)
        if not resolved_id or resolved_id == canonical_id or resolved_id in seen:
            continue

        seen.add(resolved_id)
        document = documents_by_id.get(resolved_id)
        if document is None:
            # A risk can be deleted between resolution and document lookup.
            # Do not render an incomplete row for a document that no longer
            # exists.
            continue

        risk_id = _text(document.get("risk_id"))
        if not risk_id or risk_id == canonical_id:
            continue

        metadata = document.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}

        rows.append(
            {
                "risk_id": risk_id,
                "risk": _text(document.get("title"), "—"),
                "severity": _first_text(
                    document.get("severity_label"),
                    _format_severity(document.get("severity")),
                ),
                "primary_exposure": _primary_exposure(metadata),
            }
        )

    return rows
