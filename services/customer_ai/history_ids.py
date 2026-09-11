"""Resolve the Brain conversation id from channel payloads. Do not invent threads."""

from __future__ import annotations

from typing import Any


def conversation_id_for_brain(*, payload: dict[str, Any] | None = None, conversation_key: str = "") -> str:
    data = payload or {}
    explicit = str(
        data.get("conversation_id")
        or data.get("current_conversation_id")
        or data.get("active_conversation_id")
        or ""
    ).strip()
    if explicit:
        return explicit
    key = str(conversation_key or data.get("conversation_key") or "").strip()
    if not key:
        return ""
    if key.startswith("web:"):
        return key
    if ":tiktok:" in key:
        return key.rsplit(":", 1)[-1].strip()
    return key


def comment_conversation_id(
    *,
    tenant_id: str,
    conversation_id: str = "",
    channel: str = "",
    post_id: str = "",
) -> str:
    """Keep static and AI comments on one thread. Do not mint a new scheme."""
    explicit = (conversation_id or "").strip()
    if explicit:
        return explicit
    tid = (tenant_id or "").strip()
    if not tid:
        return ""
    ch = (channel or "comment").strip() or "comment"
    post = (post_id or "").strip() or "thread"
    return f"comment:{tid}:{ch}:{post}"


def conversation_id_from_user_data(user_data: dict[str, Any] | None = None, *, fallback: str = "") -> str:
    """Bind Brain to an existing pipeline id. Do not mint a new thread scheme."""
    cid = conversation_id_for_brain(payload=user_data)
    if cid:
        return cid
    return str(fallback or "").strip()


def web_inbound_message_id(conversation_id: str, text: str) -> str:
    from hashlib import sha256

    return f"user:{(conversation_id or '').strip()}:{sha256((text or '').encode()).hexdigest()[:16]}"


def bind_dm_ids(
    *,
    conversation_id: str = "",
    user_id: str = "",
    message_id: str = "",
    message: str = "",
    followup_goal: str = "",
    payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Existing thread + inbound ids only. Do not mint a new conversation scheme."""
    conv = (conversation_id or "").strip() or (user_id or "").strip()
    mid = (message_id or "").strip() or message_id_for_brain(payload)
    if not mid:
        seed = (message or followup_goal or "").strip()
        if conv and seed:
            mid = web_inbound_message_id(conv, seed)
    return conv, mid


def message_id_for_brain(payload: dict[str, Any] | None = None) -> str:
    data = payload or {}
    batch = data.get("_batch_inbound_mids") or data.get("inbound_mids") or []
    last_batch = ""
    if isinstance(batch, list) and batch:
        last_batch = str(batch[-1] or "").strip()
    return str(
        data.get("provider_message_id")
        or data.get("message_id")
        or data.get("wamid")
        or data.get("mid")
        or data.get("_combine_mid")
        or data.get("_source_message_id")
        or data.get("source_message_id")
        or data.get("provider_event_id")
        or last_batch
        or ""
    ).strip()
