"""Owner Copilot tools: CM completeness inspect + section guide + fill-missing plan."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


async def tool_inspect_cm_guide(
    *,
    tenant_id: str,
    role: str,
    section: str | None = None,
    include_guides: bool = True,
    quality_pass: bool = True,
) -> ToolResult:
    """Inspect real CM fill state, section guide, and optional proactive quality audit."""
    _require(role, "contentManagers")
    from services.cm.progress import progress_summary
    from services.cm.section_guide import guide_for_section, list_section_guides

    summary = progress_summary(tenant_id, create_missing=False)
    data: dict[str, Any] = {
        "published": summary.get("published"),
        "percent": summary.get("percent"),
        "done_sections": summary.get("done_sections"),
        "weak_sections": summary.get("weak_sections"),
        "missing_sections": summary.get("missing_sections"),
        "remaining_sections": summary.get("remaining_sections"),
        "rules": [
            "DONE (filled) sections: do not ask again, do not suggest filling again, "
            "do not propose edits unless the owner explicitly asks to change them.",
            "Weak sections have some content but are incomplete for correct business understanding.",
            "Missing sections are still factory default / empty.",
            "Edits use propose_cm_patch → approval → draft only (no silent Live publish).",
            "On CM review/check/problem/verify intents: answer the specific ask AND report "
            "quality_pass findings (critique, duplicates, unclear, improve/halwse, suspicious) "
            "— never dump full CM unless explicitly requested.",
        ],
    }

    if quality_pass:
        from services.cm.quality_audit import run_cm_quality_audit

        data["quality_audit"] = run_cm_quality_audit(tenant_id, section=section)

    if section:
        name = section.strip().replace("-", "_")
        row = next((r for r in summary["sections"] if r.get("section") == name), None)
        if row is None:
            return ToolResult(
                ok=False,
                name="inspect_cm_guide",
                data={},
                error=f"Unknown CM section: {section}. Valid: {list(summary.get('done_sections') or []) + list(summary.get('remaining_sections') or [])}",
            )
        guide = guide_for_section(name)
        data["section"] = {
            **row,
            "guide": guide,
            "skip_as_done": bool(row.get("is_done")),
        }
        if row.get("is_done"):
            data["ai_directive"] = (
                f"`{name}` is DONE/filled for setup walks. Still run the proactive quality_pass "
                "critique for review/check intents. Do not propose changes unless the owner "
                "explicitly requests an edit (then propose_cm_patch with force_edit=true), "
                "or they approve a fix you offered from quality findings."
            )
        else:
            data["ai_directive"] = (
                f"Answer the owner's ask about `{name}`, then include quality_pass findings "
                "(not only this section). Explain why it matters, what to fill/fix, then "
                "propose a draft patch when ready."
            )
    else:
        data["sections"] = summary["sections"]
        if include_guides:
            # Compact guide index (no giant dump).
            data["guides"] = [
                {
                    "section": g["section"],
                    "title": g.get("title"),
                    "purpose": g.get("purpose"),
                    "app_path": g.get("app_path"),
                }
                for g in list_section_guides()
            ]
        data["ai_directive"] = (
            "For setup/fill-missing: skip done_sections; help remaining_sections "
            "(cm_fill_plan action=start). For review/check/problem/verify: answer the "
            "specific ask, then report quality_audit findings as a sharp editor critique "
            "(duplicates, contradictions, unclear, suspicious, improvements). "
            "Do not dump full CM. Offer propose→Approve→Live fixes."
        )

    return ToolResult(ok=True, name="inspect_cm_guide", data=data)


async def tool_cm_fill_plan(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    action: str = "status",
    section: str | None = None,
) -> ToolResult:
    """Durable fill-missing plan: start / status / advance / skip / cancel."""
    _require(role, "contentManagers")
    from services.cm import fill_plan as fp

    act = (action or "status").strip().lower()
    if act == "start":
        plan = fp.start_fill_plan(tenant_id=tenant_id, user_id=user_id)
        return ToolResult(
            ok=True,
            name="cm_fill_plan",
            data={
                "action": "start",
                "plan": plan,
                "ai_directive": (
                    "Plan started. Announce done count (skipped), remaining queue, "
                    "then work ONLY on plan.focus. Do not reopen done sections."
                ),
            },
        )
    if act == "status":
        data = fp.get_fill_plan_status(tenant_id=tenant_id, user_id=user_id)
        return ToolResult(ok=True, name="cm_fill_plan", data={"action": "status", **data})
    if act == "advance":
        plan = fp.advance_fill_plan(tenant_id=tenant_id, user_id=user_id)
        return ToolResult(
            ok=True,
            name="cm_fill_plan",
            data={
                "action": "advance",
                "plan": plan,
                "ai_directive": (
                    "Refreshed from live CM. Continue with plan.focus only, or congratulate if status=complete."
                ),
            },
        )
    if act == "skip":
        plan = fp.skip_fill_plan_section(tenant_id=tenant_id, user_id=user_id, section=section)
        return ToolResult(
            ok=True,
            name="cm_fill_plan",
            data={
                "action": "skip",
                "plan": plan,
                "ai_directive": "Section skipped. Move to the new plan.focus; do not return to skipped unless asked.",
            },
        )
    if act == "cancel":
        data = fp.cancel_fill_plan(tenant_id=tenant_id, user_id=user_id)
        return ToolResult(ok=True, name="cm_fill_plan", data={"action": "cancel", **data})
    return ToolResult(
        ok=False,
        name="cm_fill_plan",
        data={},
        error="action must be one of: start, status, advance, skip, cancel",
    )
