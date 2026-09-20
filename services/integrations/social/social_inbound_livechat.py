"""Persist Meta inbound to Live Chat when Terra/AI is skipped."""

from __future__ import annotations

import hashlib
from typing import Any

import config
from utils.utils import save_conversation_message_to_firestore

NO_TEXT_PLACEHOLDER = "[inbound skipped: no_text]"


def hashed_message_id(message_id: str) -> str:
    raw = str(message_id or "").strip()
    if not raw:
        return "none"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def log_social_inbound(
    *,
    tenant_id: str,
    channel: str,
    binding_id: str,
    action_id: str,
    reason: str,
    firestore_saved: bool,
    message_id: str,
) -> None:
    binding = str(binding_id or "").strip()
    print(
        f"[meta-social] inbound tenant={tenant_id} channel={channel} "
        f"action_id={action_id or 'none'} reason={reason} "
        f"firestore_saved={int(bool(firestore_saved))} "
        f"mid={hashed_message_id(message_id)} binding={binding[:12] or 'none'}",
        flush=True,
    )


def skipped_ai_outcome(*, reason: str, firestore_saved: bool, delivery: str = "skipped") -> dict[str, Any]:
    return {
        "ok": True,
        "delivery": delivery,
        "skipped": True,
        "reason": reason,
        "firestore_saved": bool(firestore_saved),
        "retryable": False,
        "terminal": True,
    }


async def persist_skipped_social_inbound(
    *,
    user_id: str,
    tenant_id: str,
    channel: str,
    binding_id: str,
    action_id: str,
    reason: str,
    message_id: str,
    text: str,
    user_name: str = "",
    simulation: bool = False,
) -> bool:
    """Save inbound for operators. Never sends customer copy. Never calls Terra."""
    saved = False
    body = str(text or "").strip() or (NO_TEXT_PLACEHOLDER if reason == "no_text" else f"[inbound skipped: {reason}]")
    if not simulation:
        try:
            if user_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_id] = {
                    "user_preferred_lang": "ar",
                    "current_conversation_id": None,
                    **config.DEFAULT_CONVERSATION_STATE,
                }
            user_data = config.user_data_whatsapp[user_id]
            user_data["channel"] = channel
            user_data["tenant_id"] = tenant_id
            user_data["phone_number"] = f"room:{user_id}"
            metadata = {
                "type": "text",
                "channel": channel,
                "ai_skipped": reason,
            }
            if message_id:
                metadata["source_message_id"] = str(message_id)
            await save_conversation_message_to_firestore(
                user_id,
                "user",
                body,
                user_data.get("current_conversation_id"),
                user_name or None,
                user_data.get("phone_number"),
                metadata=metadata,
            )
            conv_id = config.user_data_whatsapp.get(user_id, {}).get("current_conversation_id")
            if conv_id:
                user_data["current_conversation_id"] = conv_id
            saved = True
        except Exception as exc:
            print(
                f"[meta-social] inbound_persist_failed type={type(exc).__name__} reason={reason}",
                flush=True,
            )
            saved = False
    log_social_inbound(
        tenant_id=tenant_id,
        channel=channel,
        binding_id=binding_id,
        action_id=action_id,
        reason=reason,
        firestore_saved=saved,
        message_id=message_id,
    )
    return saved
