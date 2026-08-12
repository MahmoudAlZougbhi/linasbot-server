"""Firestore conversation message persistence (Qiscus room_id vs phone)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import config
from services.live_chat_contracts import utc_now
from utils.utils_context import append_turn_to_user_context_memory
from utils.utils_conversation_save_existing import save_message_when_conversation_id
from utils.utils_conversation_save_latest import save_message_without_conversation_id
from utils.utils_firestore import get_firestore_db
from utils.utils_identity import (
    _clean_phone_for_lookup,
    _is_placeholder_phone,
    _resolve_phone_from_room_mapping,
    get_canonical_user_id_and_phone,
)
from utils.utils_livechat_hooks import _update_customer_name_from_external_after_save

_log = logging.getLogger(__name__)


async def save_conversation_message_to_firestore(
    user_id: str,
    role: str,
    text: str,
    conversation_id: str | None = None,
    user_name: str | None = None,
    phone_number: str | None = None,
    metadata: dict | None = None,
) -> Any:
    """
    Saves a message (user or bot) to Firestore.
    If conversation_id is provided, appends to existing conversation.
    Otherwise, creates a new conversation.

    Args:
        user_id: The user's WhatsApp ID (could be room_id for Qiscus or phone for others)
        role: 'user' or 'ai' or 'operator'
        text: The message text
        conversation_id:  conversation ID. If None, creates a new conversation.
        user_name:  user name to save with the conversation
        phone_number:  actual phone number (for Qiscus where user_id is room_id)
        metadata:  metadata dict (e.g., operator_id, handled_by)
    """
    append_turn_to_user_context_memory(user_id, role, text)

    if hasattr(config, "TESTING_MODE") and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase save for user {user_id}, role {role}")
        return

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping conversation save.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"

    canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id, phone_number)
    user_doc_ref = (
        db.collection("artifacts").document(app_id_for_firestore).collection("users").document(canonical_user_id)
    )
    conversations_collection_for_user = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

    if not phone_number:
        if conversation_id:
            try:
                existing_conv_ref = conversations_collection_for_user.document(conversation_id)
                existing_conv_snap = await asyncio.to_thread(existing_conv_ref.get)
                if existing_conv_snap.exists:
                    existing_phone = existing_conv_snap.to_dict().get("customer_info", {}).get("phone_full")
                    if existing_phone:
                        phone_number = existing_phone
            except Exception as e:
                print(f"⚠️ Could not retrieve phone from conversation: {e}")

        if not phone_number:
            try:
                user_doc_check = await asyncio.to_thread(user_doc_ref.get)
                if user_doc_check.exists:
                    existing_phone = user_doc_check.to_dict().get("phone_full")
                    if existing_phone:
                        phone_number = existing_phone
            except Exception:
                pass

        if not phone_number:
            mapped_phone = _resolve_phone_from_room_mapping(user_id)
            if mapped_phone:
                phone_number = mapped_phone

        if not phone_number:
            is_likely_room_id = user_id.isdigit() and len(user_id) >= 8 and not user_id.startswith("7")

            if is_likely_room_id or (user_id.isdigit() and len(user_id) >= 9):
                phone_number = f"room:{user_id}"
            else:
                phone_number = user_id

        if phone_number and phone_number != f"room:{user_id}":
            canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id, phone_number)
            user_doc_ref = (
                db.collection("artifacts")
                .document(app_id_for_firestore)
                .collection("users")
                .document(canonical_user_id)
            )
            conversations_collection_for_user = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

    _log.info(
        "identity raw_phone=%s normalized_phone=%s canonical_user_id=%s user_id_arg=%s",
        phone_number,
        normalized_phone,
        canonical_user_id,
        user_id,
    )

    placeholder_phone = _is_placeholder_phone(phone_number)
    clean_phone = _clean_phone_for_lookup(phone_number)

    customer_name = user_name or config.user_names.get(canonical_user_id) or config.user_names.get(user_id)
    external_id = None
    defer_external_for_speed = role == "user" and normalized_phone
    if normalized_phone and not defer_external_for_speed:
        try:
            from services.customer_identity_service import resolve_customer_from_external

            external = await resolve_customer_from_external(normalized_phone)
            _log.info(
                "external_lookup normalized_phone=%s exists=%s name=%s external_id=%s",
                normalized_phone,
                external.get("exists"),
                external.get("name"),
                external.get("external_id"),
            )
            if external.get("exists") and external.get("name"):
                customer_name = external["name"]
                config.user_names[canonical_user_id] = customer_name
            else:
                customer_name = customer_name or ""
            external_id = external.get("external_id")
        except Exception as e:
            _log.warning("External resolve failed for %s: %s; using unknown/phone only", normalized_phone, e)
            customer_name = customer_name or ""
    if customer_name is None:
        customer_name = ""
    if not customer_name and not normalized_phone:
        customer_name = "Unknown Customer"

    current_gender = config.user_gender.get(canonical_user_id, "") or config.user_gender.get(user_id, "")
    current_greeting_stage = config.user_greeting_stage.get(canonical_user_id, 0) or config.user_greeting_stage.get(
        user_id, 0
    )

    effective_phone_full = normalized_phone if normalized_phone else phone_number
    effective_phone_clean = _clean_phone_for_lookup(effective_phone_full) if not placeholder_phone else clean_phone

    user_doc = await asyncio.to_thread(user_doc_ref.get)
    if not user_doc.exists:
        user_doc_payload = {
            "user_id": canonical_user_id,
            "name": customer_name,
            "gender": current_gender,
            "greeting_stage": current_greeting_stage,
            "created_at": utc_now(),
            "last_activity": utc_now(),
        }
        if not placeholder_phone:
            user_doc_payload["phone_full"] = effective_phone_full
            user_doc_payload["phone_clean"] = effective_phone_clean
        if normalized_phone:
            user_doc_payload["normalized_phone"] = normalized_phone
        if external_id:
            user_doc_payload["external_id"] = external_id
        await asyncio.to_thread(user_doc_ref.set, user_doc_payload)
        _log.info("identity created new user doc canonical_user_id=%s", canonical_user_id)
    else:
        update_data = {"last_activity": utc_now(), "name": customer_name}
        if not placeholder_phone:
            update_data["phone_full"] = effective_phone_full
            update_data["phone_clean"] = effective_phone_clean
        if normalized_phone:
            update_data["normalized_phone"] = normalized_phone
        if external_id:
            update_data["external_id"] = external_id
        if current_gender:
            update_data["gender"] = current_gender
        if current_greeting_stage > 0:
            update_data["greeting_stage"] = current_greeting_stage
        await asyncio.to_thread(user_doc_ref.update, update_data)
        _log.info("identity updated existing user doc canonical_user_id=%s", canonical_user_id)

    user_gender_value = config.user_gender.get(canonical_user_id, "") or config.user_gender.get(user_id, "")
    user_greeting_stage_value = config.user_greeting_stage.get(canonical_user_id, 0) or config.user_greeting_stage.get(
        user_id, 0
    )

    existing_user_data = user_doc.to_dict() if user_doc.exists else {}
    if placeholder_phone:
        existing_phone = existing_user_data.get("phone_full")
        if existing_phone and not _is_placeholder_phone(existing_phone):
            effective_phone_full = existing_phone
            effective_phone_clean = _clean_phone_for_lookup(existing_phone)

    user_data = config.user_data_whatsapp.get(canonical_user_id) or config.user_data_whatsapp.get(user_id) or {}
    crm_exists = user_data.get("crm_customer_exists")
    customer_info = {
        "phone_full": effective_phone_full,
        "phone_clean": effective_phone_clean,
        "normalized_phone": normalized_phone or None,
        "name": customer_name,
        "gender": user_gender_value,
        "greeting_stage": user_greeting_stage_value,
        "last_updated": utc_now(),
    }
    if crm_exists is not None:
        customer_info["crm_customer_exists"] = bool(crm_exists)
    channel = str(user_data.get("channel") or "").strip().lower()
    if channel:
        customer_info["channel"] = channel

    saved_conv_id = None
    try:
        if conversation_id:
            result = await save_message_when_conversation_id(
                db=db,
                app_id_for_firestore=app_id_for_firestore,
                conversation_id=conversation_id,
                user_id=user_id,
                canonical_user_id=canonical_user_id,
                role=role,
                text=text,
                metadata=metadata,
                channel=channel,
                customer_info=customer_info,
                conversations_collection_for_user=conversations_collection_for_user,
            )
        else:
            result = await save_message_without_conversation_id(
                db=db,
                app_id_for_firestore=app_id_for_firestore,
                user_id=user_id,
                canonical_user_id=canonical_user_id,
                role=role,
                text=text,
                metadata=metadata,
                channel=channel,
                customer_info=customer_info,
                customer_name=customer_name,
                conversations_collection_for_user=conversations_collection_for_user,
            )
        if result is None:
            return
        saved_conv_id, conversations_collection_for_user = result

        if defer_external_for_speed and saved_conv_id and normalized_phone:
            asyncio.create_task(
                _update_customer_name_from_external_after_save(
                    canonical_user_id,
                    normalized_phone,
                    saved_conv_id,
                    conversations_collection_for_user,
                    user_doc_ref,
                )
            )

    except Exception as e:
        print(f"❌ ERROR saving conversation message to Firestore for user {user_id}: {e}")
        import traceback

        traceback.print_exc()
