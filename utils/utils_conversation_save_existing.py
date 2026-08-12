"""Append/create when conversation_id is already known."""

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
)
from utils.utils_takeover import _clear_takeover_flags_for_user, firestore_post_release_waiting_blocked


async def save_message_when_conversation_id(
    *,
    db: Any,
    app_id_for_firestore: str,
    conversation_id: str,
    user_id: str,
    canonical_user_id: str,
    role: str,
    text: str,
    metadata: dict | None,
    channel: str,
    customer_info: dict,
    conversations_collection_for_user: Any,
) -> tuple[str | None, Any] | None:
    # Resolve doc across all user id variants (same as release/handover) — avoid stale duplicate path
    doc_ref, doc_snap, coll_found = await _resolve_conversation_doc_for_save(
        db,
        app_id_for_firestore,
        conversation_id,
        user_id,
        canonical_user_id,
    )
    if coll_found is not None:
        conversations_collection_for_user = coll_found

    if doc_snap and doc_snap.exists:
        saved_conv_id = conversation_id
        doc_data = doc_snap.to_dict() or {}
        current_messages = doc_data.get("messages", [])
        message_data = _build_saved_message_payload(text, metadata, channel, role)
        is_smart_source = (message_data.get("metadata", {}) or {}).get("source") == "smart_message"

        if _is_duplicate_message(current_messages, message_data):
            print(f"🔁 Duplicate message skipped for conversation {conversation_id}")
            _invalidate_live_chat_cache()
            return None

        if _is_placeholder_phone(customer_info.get("phone_full")):
            existing_customer_info = doc_data.get("customer_info", {}) or {}
            existing_phone = existing_customer_info.get("phone_full")
            if existing_phone and not _is_placeholder_phone(existing_phone):
                customer_info["phone_full"] = existing_phone
                customer_info["phone_clean"] = _clean_phone_for_lookup(existing_phone)

        current_messages.append(message_data)
        previous_state = doc_data.get("conversation_state")
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
        if role == "ai":
            update_payload["last_ai_response_at"] = message_data.get("timestamp") or utc_now()
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
            # After release: doc has post_release window — never re-open waiting from stale status fields
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
        # Canonical conversation_state for index
        # When is_smart_source: never leave users stuck in human takeover (waiting OR stale operator) —
        # otherwise handle_message only sends handoff/waiting lines and the AI never replies to template replies.
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
        if role == "user" and previous_state in {"resolved", "archived"}:
            update_payload.update(
                {
                    "conversation_state": "bot_active",
                    "status": "active",
                    "human_takeover_active": False,
                    "operator_id": None,
                }
            )

        # Transactional append: re-read messages under a transaction to avoid RMW races.
        def _txn_append() -> Any:
            from google.cloud import firestore as gcf

            transaction = db.transaction()

            @gcf.transactional
            def _run(transaction: Any) -> Any:
                fresh_snap = doc_ref.get(transaction=transaction)
                if not fresh_snap.exists:
                    return "missing", None, None
                fresh_data = fresh_snap.to_dict() or {}
                msgs = list(fresh_data.get("messages") or [])
                if _is_duplicate_message(msgs, message_data):
                    return "duplicate", fresh_data, None
                msgs.append(message_data)
                payload = dict(update_payload)
                payload["messages"] = msgs
                unread_before = int(fresh_data.get("unread_count") or 0)
                if role == "user":
                    payload["unread_count"] = unread_before + 1
                elif role == "operator":
                    payload["unread_count"] = 0
                transaction.update(doc_ref, payload)
                return "ok", fresh_data, payload

            return _run(transaction)

        txn_status, txn_doc_data, txn_payload = await asyncio.to_thread(_txn_append)
        if txn_status == "duplicate":
            print(f"🔁 Duplicate message skipped (txn) for conversation {conversation_id}")
            _invalidate_live_chat_cache()
            return None
        if txn_status != "ok" or not txn_payload:
            raise RuntimeError(f"Transactional message append failed for {conversation_id}: {txn_status}")
        if txn_doc_data is not None:
            doc_data = txn_doc_data
        update_payload = txn_payload
        current_messages = update_payload.get("messages") or current_messages
        await _propagate_takeover_state_to_sibling_conversation_docs(
            db,
            app_id_for_firestore,
            conversation_id,
            user_id,
            canonical_user_id,
            doc_ref,
            update_payload,
        )
        if is_smart_source and role == "ai":
            _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
        _invalidate_live_chat_cache()
        await _ensure_live_chat_index_after_save(canonical_user_id, conversation_id, doc_data, update_payload)
        print(f"✅ Appended {role} message to conversation {conversation_id} (total: {len(current_messages)})")

        # Include smart messages so they appear in Live Chat for operators
        _broadcast_saved_message_sse(
            canonical_user_id=canonical_user_id,
            conversation_id=conversation_id,
            role=role,
            text=text,
            customer_info=customer_info,
            message_data=message_data,
        )
    else:
        # Conversation not found - create new one
        message_data = _build_saved_message_payload(text, metadata, channel, role)

        _, new_doc_ref = await asyncio.to_thread(
            conversations_collection_for_user.add,
            {
                "user_id": canonical_user_id,
                "customer_info": customer_info,
                "messages": [message_data],
                "timestamp": utc_now(),
                # Smart outbound must stay visible as an active bot thread in Live Chat (not "closed"/archived).
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
    return saved_conv_id, conversations_collection_for_user
