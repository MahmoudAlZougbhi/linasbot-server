"""Resolve latest conversation or create a new thread."""

from __future__ import annotations

import asyncio
from typing import Any

import config
from services.live_chat_contracts import utc_now
from utils.utils_conversation_save_common import (
    _broadcast_saved_message_sse,
    _build_saved_message_payload,
    _compute_conversation_state,
)
from utils.utils_identity import _clean_phone_for_lookup, _is_placeholder_phone
from utils.utils_livechat_hooks import (
    _ensure_live_chat_index_after_save,
    _invalidate_live_chat_cache,
    _is_duplicate_message,
    _propagate_takeover_state_to_sibling_conversation_docs,
    _resolve_conversation_doc_for_save,
    _resolve_latest_conversation_id,
)
from utils.utils_takeover import _clear_takeover_flags_for_user, firestore_post_release_waiting_blocked


async def save_message_without_conversation_id(
    *,
    db: Any,
    app_id_for_firestore: str,
    user_id: str,
    canonical_user_id: str,
    role: str,
    text: str,
    metadata: dict | None,
    channel: str,
    customer_info: dict,
    customer_name: Any,
    conversations_collection_for_user: Any,
) -> tuple[str | None, Any] | None:
    # No conversation_id — try to reuse latest conversation first.
    resolved_conversation_id = None

    # 1) Check in-memory cache (by canonical id so same phone = same thread)
    cached_id = config.user_data_whatsapp.get(canonical_user_id, {}).get("current_conversation_id")
    if cached_id:
        try:
            cached_ref = conversations_collection_for_user.document(cached_id)
            cached_snap = await asyncio.to_thread(cached_ref.get)
            if cached_snap.exists:
                resolved_conversation_id = cached_id
        except Exception:
            pass

    # 2) Query Firestore for latest conversation (with scan fallback if order_by fails)
    if not resolved_conversation_id:
        resolved_conversation_id = await _resolve_latest_conversation_id(conversations_collection_for_user)

    message_data = _build_saved_message_payload(text, metadata, channel, role)
    is_smart_source = (message_data.get("metadata", {}) or {}).get("source") == "smart_message"

    doc_ref = None
    doc_snap = None
    coll_resolved = None
    resolved_exists = False
    if resolved_conversation_id:
        doc_ref, doc_snap, coll_resolved = await _resolve_conversation_doc_for_save(
            db,
            app_id_for_firestore,
            resolved_conversation_id,
            user_id,
            canonical_user_id,
        )
        if coll_resolved is not None:
            conversations_collection_for_user = coll_resolved
        resolved_exists = bool(doc_snap and doc_snap.exists)
        if resolved_conversation_id and not resolved_exists:
            print(
                f"⚠️ Resolved conversation {resolved_conversation_id} not found on any user path; "
                f"creating new thread for {canonical_user_id}"
            )

    if resolved_conversation_id and resolved_exists:
        saved_conv_id = resolved_conversation_id
        doc_data = doc_snap.to_dict() or {}
        current_messages = doc_data.get("messages", [])

        if _is_duplicate_message(current_messages, message_data):
            print(f"🔁 Duplicate message skipped for conversation {resolved_conversation_id}")
            _invalidate_live_chat_cache()
            return None

        if _is_placeholder_phone(customer_info.get("phone_full")):
            existing_customer_info = doc_data.get("customer_info", {}) or {}
            existing_phone = existing_customer_info.get("phone_full")
            if existing_phone and not _is_placeholder_phone(existing_phone):
                customer_info["phone_full"] = existing_phone
                customer_info["phone_clean"] = _clean_phone_for_lookup(existing_phone)

        current_messages.append(message_data)
        prev_state = doc_data.get("conversation_state")
        unread_before = int(doc_data.get("unread_count") or 0)
        new_unread = unread_before
        if role == "user":
            new_unread = unread_before + 1
        elif role == "operator":
            new_unread = 0

        update_payload = {
            "messages": current_messages,
            "customer_info": customer_info,
            "last_updated": utc_now(),
            "last_message_text": message_data.get("text", ""),
            "last_message_at": message_data.get("timestamp") or utc_now(),
            "unread_count": new_unread,
        }
        # Smart campaign messages should not reopen/take over live conversations.
        if not is_smart_source:
            # human_takeover_active is source of truth; only infer from status when field is missing (legacy)
            existing_takeover = bool(doc_data.get("human_takeover_active", False))
            if (
                not existing_takeover
                and "human_takeover_active" not in doc_data
                and (
                    doc_data.get("status") == "waiting_human"
                    or doc_data.get("conversation_state") == "waiting_for_operator"
                )
            ):
                existing_takeover = True
            if firestore_post_release_waiting_blocked(doc_data):
                existing_takeover = False
            existing_operator = doc_data.get("operator_id")
            if existing_takeover:
                update_payload.update(
                    {
                        "status": "human" if existing_operator else "waiting_human",
                        "human_takeover_active": True,
                        "operator_id": existing_operator,
                    }
                )
            else:
                update_payload.update(
                    {
                        "status": "active",
                        "human_takeover_active": False,
                        "operator_id": None,
                    }
                )
        # When is_smart_source: release human takeover (waiting or assigned) so template replies are handled by AI
        if is_smart_source:
            if firestore_post_release_waiting_blocked(doc_data):
                update_payload.update(
                    {
                        "conversation_state": "bot_active",
                        "human_takeover_active": False,
                        "status": "active",
                        "operator_id": None,
                    }
                )
            elif doc_data.get("human_takeover_active"):
                update_payload.update(
                    {
                        "conversation_state": "bot_active",
                        "human_takeover_active": False,
                        "human_takeover_requested": False,
                        "status": "active",
                        "operator_id": None,
                    }
                )
            else:
                update_payload["conversation_state"] = _compute_conversation_state(
                    bool(doc_data.get("human_takeover_active", False)),
                    doc_data.get("operator_id"),
                    doc_data.get("status", "active"),
                )
        else:
            update_payload["conversation_state"] = _compute_conversation_state(
                update_payload.get("human_takeover_active", False),
                update_payload.get("operator_id"),
                update_payload.get("status", "active"),
            )
        if role == "user" and prev_state in {"resolved", "archived"}:
            update_payload.update(
                {
                    "conversation_state": "bot_active",
                    "status": "active",
                    "human_takeover_active": False,
                    "operator_id": None,
                }
            )
        await asyncio.to_thread(doc_ref.update, update_payload)
        await _propagate_takeover_state_to_sibling_conversation_docs(
            db,
            app_id_for_firestore,
            resolved_conversation_id,
            user_id,
            canonical_user_id,
            doc_ref,
            update_payload,
        )
        if is_smart_source and role == "ai":
            _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
        if canonical_user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[canonical_user_id] = {}
        config.user_data_whatsapp[canonical_user_id]["current_conversation_id"] = resolved_conversation_id
        _invalidate_live_chat_cache()
        await _ensure_live_chat_index_after_save(canonical_user_id, resolved_conversation_id, doc_data, update_payload)
        print(
            f"✅ Appended {role} message to existing conversation {resolved_conversation_id} for user {canonical_user_id} (total: {len(current_messages)})"
        )

        _broadcast_saved_message_sse(
            canonical_user_id=canonical_user_id,
            conversation_id=resolved_conversation_id,
            role=role,
            text=text,
            customer_info=customer_info,
            message_data=message_data,
        )
    else:
        # No existing conversation found — create a new one
        _, new_doc_ref = await asyncio.to_thread(
            conversations_collection_for_user.add,
            {
                "user_id": canonical_user_id,
                "customer_info": customer_info,
                "messages": [message_data],
                "timestamp": utc_now(),
                "status": "active",
                "sentiment": "neutral",
                "human_takeover_active": False,
                "last_updated": utc_now(),
                "conversation_state": "bot_active",
                "last_message_text": message_data.get("text", ""),
                "last_message_at": message_data.get("timestamp") or utc_now(),
                "unread_count": 0 if role != "user" else 1,
            },
        )
        saved_conv_id = new_doc_ref.id
        if canonical_user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[canonical_user_id] = {}
        config.user_data_whatsapp[canonical_user_id]["current_conversation_id"] = new_doc_ref.id
        _invalidate_live_chat_cache()
        await _ensure_live_chat_index_after_save(canonical_user_id, saved_conv_id, None, {})
        print(f"✅ Created conversation {new_doc_ref.id} for user {canonical_user_id}")

        # 📡 Broadcast SSE event for new conversation - include smart messages for Live Chat
        try:
            from modules.live_chat_api import broadcast_sse_event

            asyncio.create_task(
                broadcast_sse_event(
                    "new_conversation",
                    {
                        "user_id": canonical_user_id,
                        "conversation_id": new_doc_ref.id,
                        "phone": customer_info.get("phone_full"),
                        "name": customer_name,
                    },
                )
            )
        except Exception:
            pass
    return saved_conv_id, conversations_collection_for_user
