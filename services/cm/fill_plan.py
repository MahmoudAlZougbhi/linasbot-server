"""Durable fill-missing plan: skip DONE sections, walk remaining one-at-a-time."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from services.cm.atomic_io import atomic_write_json, read_json_object
from services.cm.paths import tenant_cm_root
from services.cm.progress import progress_summary
from services.cm.section_guide import guide_for_section
from services.cm.setup_chat import SECTION_PROMPTS


def _plan_path(tenant_id: str, user_id: str) -> Any:
    root = tenant_cm_root(tenant_id) / "fill_plans"
    root.mkdir(parents=True, exist_ok=True)
    safe_user = re.sub(r"[^a-zA-Z0-9_-]+", "_", user_id or "user")[:80]
    return root / f"{safe_user}.json"


def load_fill_plan(tenant_id: str, user_id: str) -> dict[str, Any] | None:
    path = _plan_path(tenant_id, user_id)
    if not path.exists():
        return None
    data = read_json_object(path)
    return data if isinstance(data, dict) else None


def save_fill_plan(tenant_id: str, user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    plan["updated_at"] = time.time()
    atomic_write_json(_plan_path(tenant_id, user_id), plan)
    return plan


def clear_fill_plan(tenant_id: str, user_id: str) -> None:
    path = _plan_path(tenant_id, user_id)
    if path.exists():
        path.unlink()


def _focus_payload(section: str | None, rows_by_name: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not section:
        return None
    row = rows_by_name.get(section) or {}
    guide = guide_for_section(section) or {}
    return {
        "section": section,
        "fill": row.get("fill"),
        "gaps": list(row.get("gaps") or []),
        "title": guide.get("title") or section,
        "purpose": guide.get("purpose"),
        "why": guide.get("why"),
        "what_to_fill": guide.get("what_to_fill"),
        "useful": guide.get("useful"),
        "app_path": guide.get("app_path"),
        "interview_prompt": SECTION_PROMPTS.get(section, ""),
        "instruction": (
            "Work with the owner on THIS section only. "
            "Do not re-ask done sections. Propose draft patches via propose_cm_patch; never silent Live publish."
        ),
    }


def refresh_plan_from_progress(plan: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """Recompute done/remaining from live CM; keep queue order; drop newly-done items."""
    summary = progress_summary(tenant_id, create_missing=False)
    rows = list(summary.get("sections") or [])
    rows_by_name = {str(r.get("section")): r for r in rows if isinstance(r, dict)}
    done = [str(r["section"]) for r in rows if r.get("is_done")]
    remaining_live = [str(r["section"]) for r in rows if not r.get("is_done")]

    skipped = [s for s in (plan.get("skipped") or []) if isinstance(s, str)]
    # Preserve prior remaining order, then append any new gaps; drop done + skipped.
    prior_remaining = [s for s in (plan.get("remaining") or []) if isinstance(s, str)]
    ordered: list[str] = []
    for sec in prior_remaining + remaining_live:
        if sec in done or sec in skipped or sec in ordered:
            continue
        if sec in remaining_live:
            ordered.append(sec)

    current = plan.get("current_section")
    if current in done or current in skipped or current not in ordered:
        current = ordered[0] if ordered else None

    plan["done"] = done
    plan["remaining"] = ordered
    plan["current_section"] = current
    plan["skipped"] = skipped
    plan["published"] = bool(summary.get("published"))
    plan["percent"] = int(summary.get("percent") or 0)
    plan["focus"] = _focus_payload(current if isinstance(current, str) else None, rows_by_name)
    plan["status"] = "complete" if not ordered else "active"
    return plan


def start_fill_plan(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    """Create/replace plan from live completeness — skip DONE, queue remaining."""
    summary = progress_summary(tenant_id, create_missing=False)
    rows = list(summary.get("sections") or [])
    rows_by_name = {str(r.get("section")): r for r in rows if isinstance(r, dict)}
    done = list(summary.get("done_sections") or [])
    remaining = list(summary.get("remaining_sections") or [])
    current = remaining[0] if remaining else None
    plan: dict[str, Any] = {
        "plan_id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "created_at": time.time(),
        "status": "complete" if not remaining else "active",
        "done": done,
        "remaining": remaining,
        "skipped": [],
        "current_section": current,
        "published": bool(summary.get("published")),
        "percent": int(summary.get("percent") or 0),
        "rules": [
            "Never re-ask or re-propose edits for done (filled) sections unless the owner explicitly requests a change.",
            "Work one current_section at a time.",
            "Edits go through propose_cm_patch → owner approve → draft only (no silent Live publish).",
        ],
        "focus": _focus_payload(current, rows_by_name),
    }
    return save_fill_plan(tenant_id, user_id, plan)


def get_fill_plan_status(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    plan = load_fill_plan(tenant_id, user_id)
    if plan is None:
        # Read-only snapshot without persisting — caller may start explicitly.
        summary = progress_summary(tenant_id, create_missing=False)
        remaining = list(summary.get("remaining_sections") or [])
        return {
            "active": False,
            "plan": None,
            "snapshot": {
                "done": list(summary.get("done_sections") or []),
                "remaining": remaining,
                "percent": int(summary.get("percent") or 0),
                "published": bool(summary.get("published")),
                "next_section": remaining[0] if remaining else None,
            },
            "hint": "Call action=start to begin a durable fill-missing plan.",
        }
    plan = refresh_plan_from_progress(plan, tenant_id)
    save_fill_plan(tenant_id, user_id, plan)
    return {"active": plan.get("status") == "active", "plan": plan}


def advance_fill_plan(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    """After a section is filled (or owner finished), move to next remaining."""
    plan = load_fill_plan(tenant_id, user_id)
    if plan is None:
        return start_fill_plan(tenant_id=tenant_id, user_id=user_id)
    plan = refresh_plan_from_progress(plan, tenant_id)
    # If current still not done, keep focus (owner must finish or skip).
    current = plan.get("current_section")
    remaining = list(plan.get("remaining") or [])
    if current and current in remaining:
        # Still open — only advance if it became done during refresh (already handled).
        pass
    if plan.get("current_section") is None and remaining:
        plan["current_section"] = remaining[0]
        rows = {str(r["section"]): r for r in progress_summary(tenant_id)["sections"]}
        plan["focus"] = _focus_payload(remaining[0], rows)
    save_fill_plan(tenant_id, user_id, plan)
    return plan


def skip_fill_plan_section(*, tenant_id: str, user_id: str, section: str | None = None) -> dict[str, Any]:
    plan = load_fill_plan(tenant_id, user_id)
    if plan is None:
        plan = start_fill_plan(tenant_id=tenant_id, user_id=user_id)
    plan = refresh_plan_from_progress(plan, tenant_id)
    target = (section or plan.get("current_section") or "").strip().replace("-", "_")
    if not target:
        return plan
    skipped = [s for s in (plan.get("skipped") or []) if isinstance(s, str)]
    if target not in skipped:
        skipped.append(target)
    plan["skipped"] = skipped
    remaining = [s for s in (plan.get("remaining") or []) if s != target]
    plan["remaining"] = remaining
    plan["current_section"] = remaining[0] if remaining else None
    rows = {str(r["section"]): r for r in progress_summary(tenant_id)["sections"]}
    plan["focus"] = _focus_payload(plan.get("current_section"), rows)
    plan["status"] = "complete" if not remaining else "active"
    return save_fill_plan(tenant_id, user_id, plan)


def cancel_fill_plan(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    clear_fill_plan(tenant_id, user_id)
    return {"cancelled": True, "active": False}
