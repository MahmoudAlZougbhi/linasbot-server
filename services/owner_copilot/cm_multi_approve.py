"""List pending CM proposals and approve a selected subset (siblings stay pending)."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_copilot.tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def list_pending_cm_proposals(*, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    from services.owner_copilot.cm_approval import cm_patch_proposal_store

    props = cm_patch_proposal_store.list_pending(tenant_id=tenant_id, user_id=user_id)
    rows: list[dict[str, Any]] = []
    for prop in props:
        preview = dict(prop.preview or {})
        rows.append(
            {
                "proposal_id": prop.id,
                "section": prop.section,
                "status": prop.status,
                "created_at": prop.created_at,
                "confirmation_token": f"approve_cm_patch:{prop.id}",
                "change_kind": preview.get("change_kind") or preview.get("kind") or "edit",
                "item_title": preview.get("item_title") or preview.get("field") or prop.section,
                "before": preview.get("before") or preview.get("current_value") or "",
                "after": preview.get("after") or preview.get("proposed_value") or "",
                "preview": preview,
            }
        )
    return rows


def tool_list_pending_cm_proposals(*, tenant_id: str, user_id: str, role: str) -> ToolResult:
    _require(role, "contentManagers")
    rows = list_pending_cm_proposals(tenant_id=tenant_id, user_id=user_id)
    return ToolResult(
        ok=True,
        name="list_pending_cm_proposals",
        data={"pending": rows, "count": len(rows)},
    )


async def tool_approve_cm_batch(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    proposal_ids: list[str],
    confirmed: bool,
) -> ToolResult:
    _require(role, "contentManagers")
    ids = [str(x).strip() for x in proposal_ids if str(x).strip()]
    if not ids:
        return ToolResult(
            ok=False,
            name="approve_cm_batch",
            data={},
            error="proposal_ids required",
        )
    if not confirmed:
        token = "approve_cm_batch:" + ",".join(ids)
        return ToolResult(
            ok=True,
            name="approve_cm_batch",
            data={
                "proposal_ids": ids,
                "requires_confirmation": True,
                "pending_siblings": list_pending_cm_proposals(tenant_id=tenant_id, user_id=user_id),
            },
            requires_confirmation=True,
            confirmation_token=token,
            error="Owner confirmation required (Approve selected / confirm_tool)",
        )
    from services.owner_copilot.cm_approval import approve_cm_patch_and_activate

    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for pid in ids:
        try:
            result = await approve_cm_patch_and_activate(
                tenant_id=tenant_id,
                user_id=user_id,
                proposal_id=pid,
                actor_id=user_id,
            )
            applied.append(result)
        except Exception as exc:  # noqa: BLE001
            errors.append({"proposal_id": pid, "error": f"{type(exc).__name__}: {exc}"})
    siblings = list_pending_cm_proposals(tenant_id=tenant_id, user_id=user_id)
    return ToolResult(
        ok=len(errors) == 0,
        name="approve_cm_batch",
        data={
            "applied": applied,
            "errors": errors,
            "pending_siblings": siblings,
            "live": all(bool(row.get("live")) for row in applied) if applied else False,
        },
        error=None if not errors else f"{len(errors)} of {len(ids)} failed",
    )
