"""Post-retrieve evidence filter: drop empty / non-customer-visible winners."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem


def _row_visible(raw: dict[str, Any] | None) -> bool:
    if not isinstance(raw, dict):
        return True
    status = str(raw.get("status") or "active").strip().lower()
    if status in {"archived", "draft", "deleted", "inactive", "withdrawn", "restricted"}:
        return False
    if raw.get("active") is False:
        return False
    if raw.get("is_customer_searchable") is False:
        return False
    return True


def _section_row(sections: dict[str, Any], family: str, source_id: str) -> dict[str, Any] | None:
    key = "opening_hours" if family == "hours" else ("prices" if family in {"prices", "services"} else family)
    payload = sections.get(key)
    if family == "services" and isinstance(payload, dict):
        catalog = payload.get("catalog")
        if isinstance(catalog, list):
            for row in catalog:
                if isinstance(row, dict) and str(row.get("id") or "") == source_id:
                    return row
    if not isinstance(payload, dict):
        return None
    rows = payload.get("items") or payload.get("catalog") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or row.get("qa_group_id") or "") == source_id:
            return row
    return None


def validate_evidence(bundle: EvidenceBundle, *, sections: dict[str, Any] | None = None) -> EvidenceBundle:
    sections = sections or {}
    kept: list[EvidenceItem] = []
    for item in bundle.items:
        text = (item.text or "").strip()
        if not text:
            continue
        row = _section_row(sections, item.source_family, item.source_id)
        if row is not None and not _row_visible(row):
            continue
        kept.append(item)
    if not kept:
        return EvidenceBundle(outcome="not_found", ambiguities=list(bundle.ambiguities), conflicts=list(bundle.conflicts))
    return bundle.model_copy(update={"items": kept, "outcome": "found"})
