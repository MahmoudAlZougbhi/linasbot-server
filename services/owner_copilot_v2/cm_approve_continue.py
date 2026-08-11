"""After CM approve: advance fill plan + auto-propose next bulk section."""

from __future__ import annotations

from typing import Any

from services.owner_ai_tools_base import ToolResult


async def continue_after_cm_approve(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    approved_ok: bool,
    approved_section: str | None = None,
    live: bool | None = None,
) -> dict[str, Any]:
    """Advance durable plans and optionally propose the next dump section."""
    if not approved_ok:
        return {"advanced": False, "next_proposal": None, "directive": ""}

    from services.cm import bulk_fill as bf
    from services.cm import fill_plan as fp
    from services.owner_ai_tools_cm_bulk import propose_next_from_bulk_plan

    if approved_section:
        plan = bf.load_bulk_plan(tenant_id, user_id)
        if plan:
            plan = bf.mark_section_status(plan, approved_section, "applied")
            bf.save_bulk_plan(tenant_id, user_id, plan)

    fill = fp.advance_fill_plan(tenant_id=tenant_id, user_id=user_id)
    next_prop: ToolResult | None = await propose_next_from_bulk_plan(
        tenant_id=tenant_id,
        role=role,
        user_id=user_id,
    )

    remaining = list(fill.get("remaining") or [])
    focus = fill.get("current_section")
    bulk = bf.load_bulk_plan(tenant_id, user_id)
    bulk_pending = 0
    if bulk:
        bulk_pending = sum(1 for r in (bulk.get("queue") or []) if isinstance(r, dict) and r.get("status") == "pending")

    live_ok = True if live is None else bool(live)
    live_prefix = (
        "Change is Live for customer replies. "
        if live_ok
        else "Draft was saved, but Live publish did not complete — do not claim customers already see it. "
    )

    if next_prop and next_prop.ok:
        directive = (
            f"{live_prefix}Continuing from the owner's dump — next section proposal is ready. "
            "Explain which section you are updating and wait for Approve / ok again."
        )
    elif remaining:
        listed = ", ".join(remaining[:10])
        extra = f" (+{len(remaining) - 10} more)" if len(remaining) > 10 else ""
        directive = (
            f"{live_prefix}Dump queue done for now. Still empty/weak: {listed}{extra}. "
            "Ask the owner for each remaining section: fill now, or skip? "
            "Work one at a time via cm_fill_plan focus; never re-open DONE sections."
        )
    else:
        if live_ok:
            directive = (
                "Change is Live for customer replies. AI Setup tracked sections look filled. "
                "Congratulate briefly — customers will use this Live knowledge."
            )
        else:
            directive = (
                "Draft saved and sections look filled, but Live publish did not complete. "
                "Tell the owner clearly; do not claim customers already see the change."
            )

    return {
        "advanced": True,
        "live": live_ok,
        "fill_plan": {
            "status": fill.get("status"),
            "current_section": focus,
            "remaining": remaining,
            "percent": fill.get("percent"),
        },
        "bulk_pending": bulk_pending,
        "next_proposal": next_prop.to_dict() if next_prop else None,
        "directive": directive,
    }
