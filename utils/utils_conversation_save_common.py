"""Shared helpers for Firestore conversation message persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from services.live_chat_contracts import (
    normalize_message as contract_normalize_message,
)
from services.live_chat_contracts import utc_now
from utils.utils_livechat_hooks import _extract_source_message_id, _message_to_dashboard_format
from utils.utils_misc import detect_language

_log = logging.getLogger(__name__)


def _compute_conversation_state(human_takeover: bool, operator_id_val: Any, status_val: str) -> str:
    if status_val == "archived":
        return "archived"
    if status_val == "resolved":
        return "resolved"
    if human_takeover:
        return "assigned_to_operator" if operator_id_val else "waiting_for_operator"
    return "bot_active"


def _build_saved_message_payload(text: Any, metadata: dict | None, channel: str, role: str) -> dict:
    safe_text = text if isinstance(text, str) else str(text or "")
    detected_language = detect_language(safe_text)["language"]
    normalized_metadata = dict(metadata or {})
    if channel:
        normalized_metadata.setdefault("channel", channel)
    source_message_id = _extract_source_message_id(normalized_metadata)
    if source_message_id:
        normalized_metadata["source_message_id"] = source_message_id

    payload = contract_normalize_message(
        {
            "role": role,
            "text": safe_text,
            "timestamp": utc_now(),
            "language": detected_language,
            "metadata": normalized_metadata,
        }
    )
    if source_message_id:
        payload["message_id"] = str(source_message_id)
    else:
        payload["message_id"] = f"msg_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    if "metadata" not in payload:
        payload["metadata"] = {}
    payload["metadata"]["message_id"] = payload["message_id"]
    return payload


def _broadcast_saved_message_sse(
    *,
    canonical_user_id: str,
    conversation_id: str,
    role: str,
    text: str,
    customer_info: dict,
    message_data: dict,
) -> None:
    try:
        from modules.live_chat_api import broadcast_sse_event

        dash_msg = _message_to_dashboard_format(message_data)
        _log.info(
            "live_chat save_message broadcast conv_id=%s role=%s msg_id=%s",
            conversation_id,
            role,
            dash_msg.get("message_id", ""),
        )
        asyncio.create_task(
            broadcast_sse_event(
                "new_message",
                {
                    "user_id": canonical_user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "text": text[:100] + "..." if len(text) > 100 else text,
                    "phone": customer_info.get("phone_full"),
                    "message": dash_msg,
                },
            )
        )
    except Exception as sse_err:
        _log.exception("SSE broadcast error after save: %s", sse_err)

