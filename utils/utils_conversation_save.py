"""Persist a conversation turn in Postgres and notify that tenant's operators."""

from __future__ import annotations

import logging
from typing import Any

import config
from services.persistence.chat_store import ChatTenantRequired, append_message
from utils.conversation_save_result import FirestoreSaveOutcome, FirestoreSaveStatus
from utils.utils_context import append_turn_to_user_context_memory
from utils.utils_conversation_save_common import _broadcast_saved_message_sse, _build_saved_message_payload
from utils.utils_identity import (
    _clean_phone_for_lookup,
    _is_placeholder_phone,
    _resolve_phone_from_room_mapping,
    get_canonical_user_id_and_phone,
)

_log = logging.getLogger(__name__)


def _remember_conversation(canonical_user_id: str, conversation_id: str) -> None:
    slot = config.user_data_whatsapp.setdefault(canonical_user_id, {})
    slot["current_conversation_id"] = conversation_id


async def save_conversation_message_to_firestore(
    user_id: str,
    role: str,
    text: str,
    conversation_id: str | None = None,
    user_name: str | None = None,
    phone_number: str | None = None,
    metadata: dict | None = None,
) -> Any:
    """Save one turn. The name remains until callers move to save_conversation_message."""
    append_turn_to_user_context_memory(user_id, role, text)
    if hasattr(config, "TESTING_MODE") and config.TESTING_MODE:
        return FirestoreSaveOutcome(status=FirestoreSaveStatus.SKIPPED, conversation_id=conversation_id)

    if not phone_number:
        phone_number = _resolve_phone_from_room_mapping(user_id) or phone_number
    canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id, phone_number)
    user_data = config.user_data_whatsapp.get(canonical_user_id) or config.user_data_whatsapp.get(user_id) or {}
    channel = str((metadata or {}).get("channel") or user_data.get("channel") or "").strip().lower()
    customer_name = user_name or config.user_names.get(canonical_user_id) or ""
    meta = dict(metadata or {})
    if user_data.get("tenant_id") or user_data.get("tenantId"):
        meta.setdefault("tenant_id", user_data.get("tenant_id") or user_data.get("tenantId"))
    state = "bot_active"
    if meta.get("human_takeover_active") is True:
        state = "assigned_to_operator" if meta.get("operator_id") else "waiting_for_operator"
    message = _build_saved_message_payload(text, meta, channel, role)
    try:
        saved = append_message(
            user_id=canonical_user_id,
            role=role,
            text_body=str(message.get("text") or text or ""),
            conversation_id=conversation_id,
            user_name=customer_name,
            phone_number=normalized_phone or phone_number or "",
            metadata=message.get("metadata") if isinstance(message.get("metadata"), dict) else meta,
            channel=channel,
            conversation_state=state,
        )
    except ChatTenantRequired:
        _log.info("conversation save skipped; tenant_id missing user=%s", canonical_user_id)
        return FirestoreSaveOutcome(status=FirestoreSaveStatus.SKIPPED, conversation_id=conversation_id)
    if saved["duplicate"]:
        return FirestoreSaveOutcome(status=FirestoreSaveStatus.DUPLICATE, conversation_id=saved["conversation_id"])
    _remember_conversation(canonical_user_id, saved["conversation_id"])
    info = {
        "name": customer_name,
        "phone_full": normalized_phone or phone_number or "",
        "phone_clean": _clean_phone_for_lookup(normalized_phone or phone_number or ""),
        "tenant_id": saved["tenant_id"],
    }
    if not _is_placeholder_phone(info["phone_full"]):
        info["phone_clean"] = _clean_phone_for_lookup(info["phone_full"])
    _broadcast_saved_message_sse(
        canonical_user_id=canonical_user_id,
        conversation_id=saved["conversation_id"],
        role=role,
        text=str(message.get("text") or text or ""),
        customer_info=info,
        message_data=message,
        unread_count=None,
    )
    return FirestoreSaveOutcome(status=FirestoreSaveStatus.CREATED, conversation_id=saved["conversation_id"])
