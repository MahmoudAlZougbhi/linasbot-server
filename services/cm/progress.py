"""Shared CM completeness SoT — filled / weak / missing for UI + Owner Copilot."""

from __future__ import annotations

from typing import Any

from services.cm.constants import CM_SECTIONS, tenant_has_published_cm
from services.cm.progress_quality import assess_section_fill
from services.cm.schemas import default_section_payload
from services.cm.storage import draft_section_path, get_draft


def section_is_default(payload: dict[str, Any] | None, section: str) -> bool:
    if not isinstance(payload, dict):
        return True
    return payload == default_section_payload(section)


def list_section_fill_status(
    tenant_id: str,
    *,
    create_missing: bool = False,
) -> list[dict[str, Any]]:
    """Per-section fill rows for setup UI and Owner Copilot.

    Fields:
      - fill: missing | weak | filled
      - status: complete | incomplete  (binary UI: complete == filled only)
      - is_done: True only when fill == filled
      - gaps / summary: why still needed
    """
    rows: list[dict[str, Any]] = []
    for section in CM_SECTIONS:
        draft_present = draft_section_path(tenant_id, section).exists()
        env = get_draft(section, tenant_id=tenant_id, create_default=create_missing)
        payload = env.payload if isinstance(env.payload, dict) else None
        # No on-disk draft and not materializing → treat as missing defaults.
        is_default = (not draft_present and not create_missing) or section_is_default(payload, section)
        quality = assess_section_fill(section, payload, is_default=is_default)
        fill = str(quality["fill"])
        is_done = bool(quality["is_done"])
        rows.append(
            {
                "section": section,
                "fill": fill,
                "status": "complete" if is_done else "incomplete",
                "is_done": is_done,
                "gaps": list(quality.get("gaps") or []),
                "summary": quality.get("summary"),
                "revision": int(getattr(env, "revision", 0) or 0),
                "draft_present": draft_present,
            }
        )
    return rows


def progress_summary(tenant_id: str, *, create_missing: bool = False) -> dict[str, Any]:
    """Aggregate fill counts for readiness surfaces + AI guide tools."""
    rows = list_section_fill_status(tenant_id, create_missing=create_missing)
    filled = [str(r["section"]) for r in rows if r.get("fill") == "filled"]
    weak = [str(r["section"]) for r in rows if r.get("fill") == "weak"]
    missing = [str(r["section"]) for r in rows if r.get("fill") == "missing"]
    # Keep interview order for remaining (CM_SECTIONS order already applied).
    remaining_ordered = [str(r["section"]) for r in rows if not r.get("is_done")]
    total = len(rows)
    done_n = len(filled)
    percent = int(round((done_n / total) * 100)) if total else 0
    if remaining_ordered:
        listed = ", ".join(remaining_ordered[:8])
        extra = f" (+{len(remaining_ordered) - 8} more)" if len(remaining_ordered) > 8 else ""
        fill_missing_prompt = (
            f"Help me finish Content Management setup. Remaining (not done): {listed}{extra}. "
            "Call cm_fill_plan action=start, skip all done/filled sections, "
            "then walk remaining one section at a time using inspect_cm_guide and propose_cm_patch."
        )
    else:
        fill_missing_prompt = (
            "Review my Content Management setup. Confirm what is already filled/DONE, "
            "what still needs polish, and help me publish when ready. "
            "Use inspect_cm_guide; do not re-ask done sections."
        )

    return {
        "sections": rows,
        "complete": done_n,
        "incomplete": len(remaining_ordered),
        "total": total,
        "percent": percent,
        "filled_sections": filled,
        "weak_sections": weak,
        "missing_sections": missing,
        # Binary CTA list: anything not done (weak + missing).
        "remaining_sections": remaining_ordered,
        "complete_sections": filled,
        "done_sections": filled,
        "published": tenant_has_published_cm(tenant_id),
        # Alias used by older account-summary consumers.
        "missing_for_setup": remaining_ordered,
        # Shared CTA copy for mobile readiness → Owner Copilot handoff.
        "fill_missing_prompt": fill_missing_prompt,
    }
