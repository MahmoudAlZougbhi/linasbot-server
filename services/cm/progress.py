"""CM section fill status — complete vs still-default / missing drafts."""

from __future__ import annotations

from typing import Any

from services.cm.constants import CM_SECTIONS, tenant_has_published_cm
from services.cm.schemas import default_section_payload
from services.cm.storage import get_draft


def section_is_complete(payload: dict[str, Any] | None, section: str) -> bool:
    """True when draft payload differs from the section default (has owner content)."""
    if not isinstance(payload, dict):
        return False
    return payload != default_section_payload(section)


def list_section_fill_status(
    tenant_id: str,
    *,
    create_missing: bool = False,
) -> list[dict[str, Any]]:
    """Per-section complete/incomplete rows for setup UI and Owner Copilot."""
    rows: list[dict[str, Any]] = []
    for section in CM_SECTIONS:
        env = get_draft(section, tenant_id=tenant_id, create_default=create_missing)
        payload = env.payload if isinstance(env.payload, dict) else {}
        complete = section_is_complete(payload, section)
        rows.append(
            {
                "section": section,
                "status": "complete" if complete else "incomplete",
                "revision": env.revision,
            }
        )
    return rows


def progress_summary(tenant_id: str, *, create_missing: bool = False) -> dict[str, Any]:
    """Aggregate fill counts + missing section ids for readiness surfaces."""
    rows = list_section_fill_status(tenant_id, create_missing=create_missing)
    complete_ids = [str(r["section"]) for r in rows if r.get("status") == "complete"]
    missing = [str(r["section"]) for r in rows if r.get("status") != "complete"]
    total = len(rows)
    filled = len(complete_ids)
    percent = int(round((filled / total) * 100)) if total else 0
    return {
        "sections": rows,
        "complete": filled,
        "incomplete": len(missing),
        "total": total,
        "percent": percent,
        "missing_sections": missing,
        "complete_sections": complete_ids,
        "published": tenant_has_published_cm(tenant_id),
    }
