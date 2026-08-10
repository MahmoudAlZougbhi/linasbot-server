"""Owner Copilot: ingest business dump → CM section proposals (draft only)."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def _load_attachment_text(*, tenant_id: str, attachment_id: str) -> str | None:
    from services.owner_copilot_v2.attachments import load_attachment_bytes, load_attachment_meta

    meta = load_attachment_meta(tenant_id=tenant_id, attachment_id=attachment_id)
    if not meta:
        return None
    mime = str(meta.get("mime") or "")
    raw = load_attachment_bytes(tenant_id=tenant_id, attachment_id=attachment_id)
    if not raw:
        return None
    if mime.startswith("text/") or mime in {"application/json", "application/jsonl"}:
        return raw.decode("utf-8", errors="replace")
    # Images/PDFs: leave to vision helper below.
    return None


async def _vision_dump_text(*, tenant_id: str, attachment_id: str) -> str | None:
    """Best-effort extract plain business text from image/PDF attachments."""
    import base64
    import json

    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.model_policy import resolve_owner_policy
    from services.owner_copilot_v2.attachments import load_attachment_bytes, load_attachment_meta
    from services.owner_copilot_v2.vision_import import multimodal_supported

    if not multimodal_supported():
        return None
    meta = load_attachment_meta(tenant_id=tenant_id, attachment_id=attachment_id)
    content = load_attachment_bytes(tenant_id=tenant_id, attachment_id=attachment_id)
    if not meta or not content:
        return None
    mime = str(meta.get("mime") or "application/octet-stream")
    policy = resolve_owner_policy(surface="owner_copilot", owner_mode="work", mutation_hint=True)
    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    kwargs = build_chat_completion_kwargs(
        model=policy.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract ALL readable business information as plain text for Content Management. "
                    "Return JSON {\"text\": \"...\"}. Never invent unread facts."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the full business description from this file."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        max_tokens=3000,
        temperature=0.1,
        reasoning_effort=str(policy.reasoning_effort),
    )
    kwargs["response_format"] = {"type": "json_object"}
    try:
        response = await client.chat.completions.create(**kwargs)
        parsed = json.loads((response.choices[0].message.content or "{}").strip())
    except Exception:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
        return parsed["text"].strip() or None
    return None


async def tool_ingest_business_dump(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    text: str = "",
    reply_style: str = "",
    attachment_id: str | None = None,
    propose_first: bool = True,
) -> ToolResult:
    """Parse business dump → queue CM patches → start fill plan → propose first section."""
    _require(role, "contentManagers")
    from services.cm import bulk_fill as bf
    from services.cm import fill_plan as fp
    from services.owner_ai_tools_write import tool_propose_cm_patch

    body = (text or "").strip()
    source = "text"
    if attachment_id:
        att_text = _load_attachment_text(tenant_id=tenant_id, attachment_id=attachment_id)
        if att_text:
            body = f"{body}\n\n{att_text}".strip() if body else att_text
            source = "attachment_text"
        else:
            vision_text = await _vision_dump_text(tenant_id=tenant_id, attachment_id=attachment_id)
            if vision_text:
                body = f"{body}\n\n{vision_text}".strip() if body else vision_text
                source = "attachment_vision"
    if len(body) < 40:
        return ToolResult(
            ok=False,
            name="ingest_business_dump",
            data={},
            error=(
                "Need a fuller business description (paste text and/or attach a txt/pdf/image). "
                "Include how you want the AI to reply when possible."
            ),
        )

    try:
        extracted = await bf.extract_sections_from_dump(text=body, reply_style=reply_style or "")
    except Exception as exc:
        return ToolResult(
            ok=False,
            name="ingest_business_dump",
            data={},
            error=f"Could not distribute dump into CM sections: {exc}",
        )

    sections = list(extracted.get("sections") or [])
    missing_notes = list(extracted.get("missing_notes") or [])
    plan = bf.store_bulk_sections(
        tenant_id=tenant_id,
        user_id=user_id,
        sections=sections if isinstance(sections, list) else [],
        source=source,
        missing_notes=[str(x) for x in missing_notes],
    )
    fill = fp.start_fill_plan(tenant_id=tenant_id, user_id=user_id)

    proposed: dict[str, Any] | None = None
    propose_error: str | None = None
    first = bf.peek_next_pending(plan)
    if propose_first and first:
        prop = await tool_propose_cm_patch(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            section=str(first["section"]),
            patch=dict(first.get("patch") or {}),
        )
        if prop.ok:
            proposed = prop.to_dict()
            plan = bf.mark_section_status(plan, str(first["section"]), "proposed")
            bf.save_bulk_plan(tenant_id, user_id, plan)
        else:
            propose_error = prop.error

    pending_n = sum(1 for r in plan.get("queue") or [] if isinstance(r, dict) and r.get("status") == "pending")
    return ToolResult(
        ok=True,
        name="ingest_business_dump",
        data={
            "bulk_plan": {
                "plan_id": plan.get("plan_id"),
                "queued": len(plan.get("queue") or []),
                "pending": pending_n,
                "rejected": plan.get("rejected") or [],
                "missing_notes": plan.get("missing_notes") or [],
                "source": source,
            },
            "fill_plan": {
                "status": fill.get("status"),
                "current_section": fill.get("current_section"),
                "remaining": fill.get("remaining"),
                "done": fill.get("done"),
            },
            "first_proposal": proposed,
            "propose_error": propose_error,
            "ai_directive": (
                "Announce which sections you filled from the dump. "
                "Show the first proposal card and wait for Approve / ok. "
                "After each approve the system auto-continues remaining dump sections. "
                "At the end, list still-empty sections and ask fill or skip."
            ),
        },
        requires_confirmation=bool(proposed and proposed.get("requires_confirmation")),
        confirmation_token=(
            str(proposed.get("confirmation_token"))
            if proposed and proposed.get("confirmation_token")
            else None
        ),
        error=(
            "Owner confirmation required before CM draft is saved (Approve button or short assent)"
            if proposed and proposed.get("requires_confirmation")
            else None
        ),
    )


async def propose_next_from_bulk_plan(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
) -> ToolResult | None:
    """Propose the next pending bulk-plan section (used after approve)."""
    from services.cm import bulk_fill as bf
    from services.owner_ai_tools_write import tool_propose_cm_patch

    plan = bf.load_bulk_plan(tenant_id, user_id)
    if not plan:
        return None
    nxt = bf.peek_next_pending(plan)
    if not nxt:
        return None
    prop = await tool_propose_cm_patch(
        tenant_id=tenant_id,
        role=role,
        user_id=user_id,
        section=str(nxt["section"]),
        patch=dict(nxt.get("patch") or {}),
    )
    if prop.ok:
        plan = bf.mark_section_status(plan, str(nxt["section"]), "proposed")
        bf.save_bulk_plan(tenant_id, user_id, plan)
    return prop
