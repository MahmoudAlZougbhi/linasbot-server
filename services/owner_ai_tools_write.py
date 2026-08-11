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
    allowed = (
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
    safe: dict[str, Any] = {k: updates[k] for k in allowed if k in updates}
    profile = update_owner_profile(user_id, safe)
    data: dict[str, Any] = {"profile": profile}
    if "preferred_language" in safe or "preferredLanguage" in safe:
        data["note"] = (
            "preferred_language is owner chat/app preference only. "
            "Customer DM/comment reply language comes from AI Setup → Languages "
            "and cannot be changed via profile or Settings."
        )
    return ToolResult(ok=True, name="update_profile", data=data)


async def tool_propose_cm_patch(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    section: str,
    patch: dict[str, Any],
    force_edit: bool = False,
    replace_proposal_id: str | None = None,
) -> ToolResult:
    _require(role, "contentManagers")
    from services.cm.progress import progress_summary
    from services.owner_ai_cm_approval import propose_cm_patch, reject_cm_patch

    sec = (section or "").strip().replace("-", "_")
    safe_patch = dict(patch) if isinstance(patch, dict) else {}
    map_locked_note: str | None = None
    if sec == "languages" and "response_language_map" in safe_patch:
        safe_patch.pop("response_language_map", None)
        map_locked_note = (
            "response_language_map is FIXED (sabtin) and cannot be changed: "
            "English→English, Arabic→Arabic, French→French, Franco→Arabic. "
            "Owners may still enable/disable supported_languages and set default_language."
        )
        if not safe_patch:
            return ToolResult(
                ok=False,
                name="propose_cm_patch",
                data={
                    "section": sec,
                    "blocked_reason": "response_language_map_locked",
                    "hint": map_locked_note,
                },
                error="response_language_map_locked",
            )

    if sec and not force_edit:
        summary = progress_summary(tenant_id, create_missing=False)
        done = set(summary.get("done_sections") or [])
        if sec in done:
            return ToolResult(
                ok=False,
                name="propose_cm_patch",
                data={
                    "section": sec,
                    "is_done": True,
                    "blocked_reason": "section_already_filled",
                    "hint": (
                        "This section is DONE/filled. Do not re-propose edits unless the owner "
                        "explicitly asked to change it — then retry with force_edit=true."
                    ),
                },
                error="section_already_filled",
            )

    if replace_proposal_id:
        try:
            reject_cm_patch(tenant_id=tenant_id, user_id=user_id, proposal_id=str(replace_proposal_id))
        except Exception:
            pass

    data = propose_cm_patch(tenant_id=tenant_id, user_id=user_id, section=section, patch=safe_patch)
    if map_locked_note:
        data = {**data, "note": map_locked_note, "stripped_fields": ["response_language_map"]}
    return ToolResult(
        ok=True,
        name="propose_cm_patch",
        data=data,
        requires_confirmation=True,
        confirmation_token=str(data.get("confirmation_token")),
        error="Owner confirmation required before CM draft is saved (Approve button or short assent: ok / موافق / yes)",
    )


async def tool_approve_cm_patch(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    proposal_id: str,
    confirmed: bool,
    delete_ids: list[str] | None = None,
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
    from services.owner_ai_cm_approval import approve_cm_patch_and_activate

    # Approve → validate → save Draft → publish Live (section overlay or first full publish).
    # Never returns a user-facing Publish confirmation after approval.
    try:
        data = await approve_cm_patch_and_activate(
            tenant_id=tenant_id,
            user_id=user_id,
            proposal_id=proposal_id,
            delete_ids=delete_ids,
            actor_id=user_id,
        )
    except PermissionError as exc:
        return ToolResult(
            ok=False,
            name="approve_cm_patch",
            data={"proposal_id": proposal_id},
            error=str(exc) or "Permission denied",
        )
    except ValueError as exc:
        return ToolResult(
            ok=False,
            name="approve_cm_patch",
            data={"proposal_id": proposal_id},
            error=str(exc) or "Invalid proposal",
        )
    except Exception as exc:  # noqa: BLE001 — surface apply/validate failures to the card
        return ToolResult(
            ok=False,
            name="approve_cm_patch",
            data={"proposal_id": proposal_id},
            error=f"{type(exc).__name__}: {exc}",
        )
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
