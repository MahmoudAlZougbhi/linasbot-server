"""Typed write / high-impact tools for the owner System Copilot."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


async def tool_update_profile(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    updates: dict[str, Any],
) -> ToolResult:
    del tenant_id, role
    from services.owner_ai_profile import update_owner_profile

    # Never accept inferred gender from email/name — only explicit client fields.
    safe = {
        k: updates[k]
        for k in (
            "gender",
            "display_name",
            "displayName",
            "preferred_language",
            "preferredLanguage",
            "form_of_address",
            "formOfAddress",
            "address_prompt_asked",
            "addressPromptAsked",
        )
        if k in updates
    }
    profile = update_owner_profile(user_id, safe)
    return ToolResult(ok=True, name="update_profile", data={"profile": profile})


async def tool_propose_cm_patch(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    section: str,
    patch: dict[str, Any],
) -> ToolResult:
    _require(role, "contentManagers")
    from services.owner_ai_cm_approval import propose_cm_patch

    data = propose_cm_patch(tenant_id=tenant_id, user_id=user_id, section=section, patch=patch)
    return ToolResult(
        ok=True,
        name="propose_cm_patch",
        data=data,
        requires_confirmation=True,
        confirmation_token=str(data.get("confirmation_token")),
        error="Confirmation required before CM draft is saved",
    )


async def tool_approve_cm_patch(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    proposal_id: str,
    confirmed: bool,
) -> ToolResult:
    _require(role, "contentManagers")
    if not confirmed:
        return ToolResult(
            ok=True,
            name="approve_cm_patch",
            data={"proposal_id": proposal_id, "action": "approve_cm_patch"},
            requires_confirmation=True,
            confirmation_token=f"approve_cm_patch:{proposal_id}",
            error="Confirmation required",
        )
    from services.owner_ai_cm_approval import approve_cm_patch

    data = approve_cm_patch(tenant_id=tenant_id, user_id=user_id, proposal_id=proposal_id, actor_id=user_id)
    return ToolResult(ok=True, name="approve_cm_patch", data=data)


async def tool_publish_cm(*, tenant_id: str, role: str, confirmed: bool) -> ToolResult:
    _require(role, "contentPublish")
    if not confirmed:
        return ToolResult(
            ok=True,
            name="publish_cm",
            data={"action": "publish_cm"},
            requires_confirmation=True,
            confirmation_token="publish_cm",
            error="Confirmation required before publish",
        )
    from services.cm.publish import publish_draft

    result = await publish_draft(tenant_id=tenant_id)
    data = result if isinstance(result, dict) else {"result": str(result)}
    return ToolResult(ok=True, name="publish_cm", data=data)
