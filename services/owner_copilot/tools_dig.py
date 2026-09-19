"""Read-only tenant CM dig + channel-flag proposals (Approve still required)."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_copilot.tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def _norm_title(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _duplicate_rows(items: list[dict[str, Any]], *, section: str) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    dupes: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        title = _norm_title(str(row.get("title") or row.get("name") or ""))
        if not title:
            continue
        prior = seen.get(title)
        rid = str(row.get("id") or row.get("qa_group_id") or "")
        if prior:
            dupes.append({"section": section, "title": title, "ids": [prior, rid]})
        else:
            seen[title] = rid
    return dupes


def _load_items(tenant_id: str, section: str) -> list[dict[str, Any]]:
    from services.ai_setup.storage import get_draft

    env = get_draft(section, tenant_id=tenant_id, create_default=False)
    payload = env.payload if isinstance(env.payload, dict) else {}
    rows = payload.get("items")
    return [dict(r) for r in rows] if isinstance(rows, list) else []


async def tool_dig_tenant_cm(*, tenant_id: str, role: str, user_id: str) -> ToolResult:
    _require(role, "contentManagers")
    from services.ai_setup.progress import progress_summary
    from services.ai_setup.quality_audit import run_cm_quality_audit
    from services.ai_setup.storage import get_draft

    summary = progress_summary(tenant_id, create_missing=False)
    audit = run_cm_quality_audit(tenant_id)
    dupes: list[dict[str, Any]] = []
    for section in ("knowledge", "care", "faq"):
        dupes.extend(_duplicate_rows(_load_items(tenant_id, section), section=section))
    actions = get_draft("actions", tenant_id=tenant_id, create_default=False)
    action_items: list[Any] = []
    if isinstance(actions.payload, dict):
        raw_items = actions.payload.get("items")
        if isinstance(raw_items, list):
            action_items = list(raw_items)
    traces: list[dict[str, Any]] = []
    try:
        from services.owner_copilot.tools_diagnosis import tool_get_recent_customer_interactions

        recent = await tool_get_recent_customer_interactions(tenant_id=tenant_id, role=role, limit=8)
        if recent.ok and isinstance(recent.data, dict):
            raw_traces = recent.data.get("items") or recent.data.get("interactions")
            if isinstance(raw_traces, list):
                traces = [row for row in raw_traces if isinstance(row, dict)][:8]
    except Exception:
        traces = []
    return ToolResult(
        ok=True,
        name="dig_tenant_cm",
        data={
            "progress": {
                "percent": summary.get("percent"),
                "missing": summary.get("missing_sections"),
                "weak": summary.get("weak_sections"),
                "filled": summary.get("filled_sections"),
            },
            "duplicates": dupes,
            "quality_audit": audit,
            "channels": action_items,
            "recent_interactions": traces,
            "ai_directive": (
                "Report missing, duplicated, and weak areas. "
                "Propose fixes via propose_* cards — never write Live without Approve. "
                "Channel enable/disable uses propose_channel_flags."
            ),
        },
    )


async def tool_propose_channel_flags(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    patch: dict[str, Any],
) -> ToolResult:
    _require(role, "contentManagers")
    from services.owner_copilot.tools_write import tool_propose_cm_patch

    if not isinstance(patch, dict) or not patch:
        return ToolResult(
            ok=False,
            name="propose_channel_flags",
            data={},
            error="patch object required (actions items enable/disable)",
        )
    return await tool_propose_cm_patch(
        tenant_id=tenant_id,
        role=role,
        user_id=user_id,
        section="actions",
        patch=patch,
        force_edit=True,
    )
