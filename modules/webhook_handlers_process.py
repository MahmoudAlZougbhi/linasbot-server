"""Parsed webhook message routing (LOC split)."""

from __future__ import annotations

import asyncio
import datetime
from typing import Any

import config
from modules.webhook_handlers_dedupe import (
    _extract_text_from_content,
    _process_parsed_release_claim_on_error,
    _process_parsed_should_skip_duplicate,
    _webhook_text_body_fingerprint,
)
from modules.webhook_handlers_parse import (
    _count_images_in_single_message,
    _count_non_empty_lines,
)
from services.api_integrations import log_report_event
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from utils.utils import set_human_takeover_status

async def process_parsed_message(parsed_message: dict[str, Any], adapter: Any) -> None:
    """Entry: dedupe same message_id in-process, then delegate."""
    mid_for_dedupe = (parsed_message.get("message_id") or "").strip()
    if mid_for_dedupe:
        if await _process_parsed_should_skip_duplicate(mid_for_dedupe):
            return
    try:
        await _process_parsed_message_impl(parsed_message, adapter)
    except Exception:
        _process_parsed_release_claim_on_error(mid_for_dedupe)
        raise


async def _process_parsed_message_impl(parsed_message: dict[str, Any], adapter: Any) -> None:
    """Process a parsed message regardless of provider. Uses normalized phone as canonical user_id to prevent duplicates."""
    from services.customer_identity_service import resolve_customer_from_external
    from utils.phone_utils import is_phone_like_user_id
    from utils.utils import get_canonical_user_id_and_phone, persist_room_to_phone_mapping

    raw_user_id = parsed_message["user_id"]
    user_name = parsed_message["user_name"]
    phone_number = parsed_message.get("phone_number")
    # Resolve canonical user_id (E.164 normalized_phone) so same number = same user/thread
    canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(raw_user_id, phone_number)
    user_id = canonical_user_id
    parsed_message["user_id"] = user_id
    parsed_message["phone_number"] = normalized_phone or phone_number or ""

    # Persist room_id -> phone when provider sends room_id but we extracted phone (e.g. Qiscus).
    # Prevents duplicate conversations when same user sends via room_id in future messages.
    if normalized_phone and not is_phone_like_user_id(raw_user_id):
        persist_room_to_phone_mapping(raw_user_id, normalized_phone)

    print(
        f"DEBUG: identity raw_user_id={raw_user_id} normalized_phone={normalized_phone} canonical_user_id={canonical_user_id}"
    )
    if raw_user_id != canonical_user_id:
        print(f"🔄 Identity resolved: {raw_user_id} → {canonical_user_id}")

    # Migrate in-memory state from raw to canonical so we don't lose conversation_id etc.
    if raw_user_id != user_id and raw_user_id in config.user_data_whatsapp:
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = dict(config.user_data_whatsapp[raw_user_id])
        else:
            config.user_data_whatsapp[user_id].update(config.user_data_whatsapp[raw_user_id])
        for key in ("user_names", "user_gender", "user_greeting_stage"):
            d = getattr(config, key, None)
            if d and raw_user_id in d and user_id not in d:
                d[user_id] = d[raw_user_id]

    # Per-message guardrails (not conversation-wide): limit text lines and image count.
    message_type = parsed_message.get("type", "")
    content = parsed_message.get("content", {})

    if message_type == "text":
        user_text = _extract_text_from_content(content)
        line_count = _count_non_empty_lines(user_text)
        if line_count > config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE:
            await adapter.send_text_message(
                user_id,
                f"لطفاً خفّف طول الرسالة: الحد الأقصى للرسالة الواحدة هو {config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE} سطر. "
                "قسّمها على أكثر من رسالة قصيرة.",
            )
            log_report_event(
                "single_message_text_line_limit_blocked",
                user_name or user_id,
                config.user_gender.get(user_id, "unspecified"),
                {
                    "line_count": line_count,
                    "max_allowed_lines": config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE,
                    "provider": WhatsAppFactory.get_current_provider(),
                },
            )
            return

    image_count = _count_images_in_single_message(message_type, content)
    if image_count > config.MAX_IMAGES_PER_SINGLE_MESSAGE:
        await adapter.send_text_message(
            user_id, f"لطفاً قلّل عدد الصور: الحد الأقصى للرسالة الواحدة هو {config.MAX_IMAGES_PER_SINGLE_MESSAGE} صور."
        )
        log_report_event(
            "single_message_image_limit_blocked",
            user_name or user_id,
            config.user_gender.get(user_id, "unspecified"),
            {
                "image_count": image_count,
                "max_allowed_images": config.MAX_IMAGES_PER_SINGLE_MESSAGE,
                "provider": WhatsAppFactory.get_current_provider(),
            },
        )
        return

    # For text: defer external lookup so user message can save+broadcast first (instant in Live Chat)
    defer_external = message_type == "text" and bool(normalized_phone)
    external_exists = None
    if normalized_phone and not defer_external:
        try:
            external = await resolve_customer_from_external(normalized_phone)
            external_exists = bool(external.get("exists"))
            print(
                f"DEBUG: external_lookup normalized_phone={normalized_phone} exists={external.get('exists')} name={external.get('name')}"
            )
            if external.get("exists") and external.get("name"):
                config.user_names[user_id] = external["name"]
                user_name = external["name"]
                parsed_message["user_name"] = user_name
            else:
                config.user_names.pop(user_id, None)
                user_name = ""
                parsed_message["user_name"] = user_name
            if external.get("gender") and external["gender"] in ("male", "female"):
                config.user_gender[user_id] = external["gender"]
                if config.user_greeting_stage.get(user_id, 0) <= 1:
                    config.user_greeting_stage[user_id] = 2
        except Exception as e:
            print(f"WARNING: External resolve failed for {normalized_phone}: {e}; using phone only")
            config.user_names.pop(user_id, None)
            parsed_message["user_name"] = ""
    elif defer_external:
        user_name = parsed_message.get("user_name") or config.user_names.get(user_id) or ""
        parsed_message["user_name"] = user_name

        # Resolve CRM name in background (user message will show in Live Chat immediately)
        async def _set_name_from_external(resolved_phone: str = str(normalized_phone or "")) -> None:
            try:
                if not resolved_phone:
                    return
                ext = await resolve_customer_from_external(resolved_phone)
                user_state = config.user_data_whatsapp.get(user_id)
                if user_state is not None:
                    user_state["crm_customer_exists"] = bool(ext.get("exists"))
                    user_state["customer_file_status"] = "existing_file" if ext.get("exists") else "new_customer"
                if ext.get("exists") and ext.get("name"):
                    config.user_names[user_id] = ext["name"]
                else:
                    config.user_names.pop(user_id, None)
                if ext.get("gender") and ext["gender"] in ("male", "female"):
                    config.user_gender[user_id] = ext["gender"]
            except Exception:
                pass

        asyncio.create_task(_set_name_from_external())

    message_type = parsed_message["type"]
    content = parsed_message["content"]

    # Initialize user_data_whatsapp if not exists (AI Smart Employee state schema)
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            "user_preferred_lang": "ar",
            "initial_user_query_to_process": None,
            "awaiting_human_handover_confirmation": False,
            "current_conversation_id": None,
            "crm_customer_exists": None,
            "customer_file_status": None,
            **config.DEFAULT_CONVERSATION_STATE,
        }
        print(f"✅ Initialized user_data_whatsapp for user {user_id}")

    # Store phone number IMMEDIATELY
    if phone_number:
        config.user_data_whatsapp[user_id]["phone_number"] = phone_number
        print(f"✅ CRITICAL: Stored phone_number {phone_number} for user {user_id} BEFORE any processing")
    else:
        print(f"⚠️ WARNING: No phone_number extracted for user {user_id}")

    if external_exists is not None:
        config.user_data_whatsapp[user_id]["crm_customer_exists"] = external_exists
        config.user_data_whatsapp[user_id]["customer_file_status"] = (
            "existing_file" if external_exists else "new_customer"
        )

    # Persist source message id as one-shot metadata for Firestore dedupe.
    source_message_id = parsed_message.get("message_id")
    if source_message_id:
        config.user_data_whatsapp[user_id]["_source_message_id"] = str(source_message_id)
    else:
        config.user_data_whatsapp[user_id].pop("_source_message_id", None)

    # Collect webhook text body fingerprints for cross-worker AI turn claim (same text, different wamid).
    if message_type == "text":
        _tbfp = _webhook_text_body_fingerprint(parsed_message)
        if _tbfp:
            config.user_data_whatsapp[user_id].setdefault("_batch_turn_body_fps", []).append(_tbfp)

    # ===== RESTORE USER STATE FROM FIRESTORE FIRST (handles server restart) =====
    # Always try to restore from Firestore before API lookup
    # Only restore if gender is not already set to a valid value
    current_gender = config.user_gender.get(user_id)
    print(f"🔍 DEBUG: Before Firestore restore - current_gender in memory: '{current_gender}'")
    if current_gender not in ["male", "female"]:
        try:
            from utils.utils import get_user_state_from_firestore

            print(f"🔄 Attempting to restore user state from Firestore for {user_id}...")
            firestore_state = await get_user_state_from_firestore(user_id)
            print(f"🔍 DEBUG: Firestore returned state: {firestore_state}")

            if firestore_state:
                # Restore gender if valid
                firestore_gender = firestore_state.get("gender", "")
                if firestore_gender in ["male", "female"]:
                    config.user_gender[user_id] = firestore_gender
                    print(f"✅ Restored gender from Firestore: {firestore_gender}")

                # Restore greeting stage if > 0
                firestore_greeting_stage = firestore_state.get("greeting_stage", 0)
                if firestore_greeting_stage > 0:
                    config.user_greeting_stage[user_id] = firestore_greeting_stage
                    print(f"✅ Restored greeting_stage from Firestore: {firestore_greeting_stage}")

                # Restore name if available
                firestore_name = firestore_state.get("name", "")
                if firestore_name and firestore_name != "Unknown Customer":
                    config.user_names[user_id] = firestore_name
                    user_name = firestore_name
                    print(f"✅ Restored name from Firestore: {firestore_name}")
            else:
                print(f"ℹ️ No user state found in Firestore for {user_id}")
        except Exception as e:
            print(f"❌ Error restoring user state from Firestore: {e}")
            import traceback

            traceback.print_exc()

    # Debug: Log state after Firestore restoration attempt
    print(
        f"🔍 DEBUG: After Firestore restore - gender: '{config.user_gender.get(user_id)}', greeting_stage: {config.user_greeting_stage.get(user_id, 0)}"
    )

    # (Name/gender from external CRM are already set above via resolve_customer_from_external)

    # New-user inbound messages should not auto-trigger /start welcome.
    # Session greeting is now handled in handle_message based on conversation/inactivity policy.
    is_new_user = (
        user_id not in config.user_names
        or user_id not in config.user_greeting_stage
        or config.user_greeting_stage.get(user_id, 0) == 0
    )
    if is_new_user:
        print(f"🆕 NEW USER detected: {user_id}, using session greeting flow (no auto /start).")
        config.user_greeting_stage[user_id] = max(config.user_greeting_stage.get(user_id, 0), 1)
        if config.user_gender.get(user_id) not in ["male", "female"]:
            config.user_gender[user_id] = "unknown"
    else:
        print(f"👤 EXISTING USER: {user_id}, normal flow.")

    # Handle different message types
    if message_type == "text":
        # Handle both dict format (old) and string format (new)
        if isinstance(content, dict):
            user_input_text = content.get("text", "")
        else:
            user_input_text = str(content)

        if config.user_data_whatsapp.get(user_id, {}).get("awaiting_post_session_feedback_rating"):
            from services.post_session_feedback_rating_service import (
                try_handle_post_session_feedback_reply,
            )

            if await try_handle_post_session_feedback_reply(user_id, user_input_text, adapter):
                return

        if config.user_data_whatsapp.get(user_id, {}).get("awaiting_session_rating"):
            from services.session_rating_service import try_handle_session_rating_reply

            if await try_handle_session_rating_reply(user_id, user_input_text, adapter):
                return

        if user_input_text.lower() == "/exit":
            from modules.webhook_handlers import exit_training_mode_whatsapp

            await exit_training_mode_whatsapp(user_id)
        elif user_input_text.lower() == "/daily_report":
            from modules.webhook_handlers import generate_daily_report_command_whatsapp

            await generate_daily_report_command_whatsapp(user_id)
        elif user_input_text.lower() == "/takeover":
            current_conv_id = config.user_data_whatsapp[user_id].get("current_conversation_id")
            if current_conv_id:
                await set_human_takeover_status(
                    user_id,
                    current_conv_id,
                    True,
                    None,
                    None,
                    None,
                    True,  # force_waiting_queue (admin /takeover)
                )
                await adapter.send_text_message(
                    user_id, "تم تفعيل وضع التحكم البشري لهذه المحادثة. البوت لن يرد عليها."
                )
            else:
                await adapter.send_text_message(user_id, "لا توجد محادثة جارية لتفعيل التحكم البشري عليها.")
        elif user_input_text.lower() == "/release":
            current_conv_id = config.user_data_whatsapp[user_id].get("current_conversation_id")
            if current_conv_id:
                await set_human_takeover_status(user_id, current_conv_id, False)
                await adapter.send_text_message(user_id, "تم إلغاء وضع التحكم البشري لهذه المحادثة. البوت سيعود للرد.")
            else:
                await adapter.send_text_message(user_id, "لا توجد محادثة جارية لإلغاء التحكم البشري عليها.")
        else:
            from modules.webhook_handlers import handle_message_whatsapp_with_adapter

            await handle_message_whatsapp_with_adapter(user_id, user_input_text, user_name, adapter, phone_number)

    elif message_type == "image":
        image_id = content.get("image_id")
        if image_id:
            # Process image with GPT-4 Vision analysis for all providers
            print("DEBUG: Image received - processing with GPT-4 Vision analysis")
            from modules.webhook_handlers_photo import handle_photo_message_whatsapp_with_adapter

            await handle_photo_message_whatsapp_with_adapter(user_id, image_id, user_name, adapter)

    elif message_type in ("audio", "voice", "ptt"):
        audio_id = None
        if isinstance(content, dict):
            audio_id = content.get("audio_id") or content.get("link") or content.get("url")
        elif isinstance(content, str) and content.strip():
            audio_id = content.strip()
        if audio_id:
            from modules.webhook_handlers_voice import handle_voice_message_whatsapp_with_adapter

            await handle_voice_message_whatsapp_with_adapter(user_id, audio_id, user_name, adapter)
        else:
            print(f"⚠️ Audio/voice message received but no audio_id/link: content={type(content).__name__}")

    elif message_type == "file_attachment":
        file_url = content.get("image_id") or content.get("audio_id") or content.get("document_id")
        if file_url:
            if content.get("image_id"):
                from modules.webhook_handlers_photo import handle_photo_message_whatsapp_with_adapter

                await handle_photo_message_whatsapp_with_adapter(user_id, file_url, user_name, adapter)
            elif content.get("audio_id"):
                from modules.webhook_handlers_voice import handle_voice_message_whatsapp_with_adapter

                await handle_voice_message_whatsapp_with_adapter(user_id, file_url, user_name, adapter)
            else:
                await adapter.send_text_message(user_id, "تم استلام الملف، شكراً لك!")

    else:
        await adapter.send_text_message(
            user_id, "عذراً، أنا أستطيع معالجة الرسائل النصية، الصور، والرسائل الصوتية فقط حالياً. 😅"
        )
        print(f"Unhandled message type: {message_type} from {user_id}")

    # Clear one-shot source ID if it wasn't consumed in handlers.
    config.user_data_whatsapp.get(user_id, {}).pop("_source_message_id", None)


# ============================================================================
# WhatsApp Adapter Functions
# ============================================================================


async def start_command_whatsapp(user_whatsapp_id: str, user_name: str) -> None:
    """Adapts start_command for WhatsApp."""
    print(f"DEBUG: start_command_whatsapp called for user {user_whatsapp_id}")

    config.user_names[user_whatsapp_id] = user_name

    config.user_context[user_whatsapp_id].clear()
    config.gender_attempts[user_whatsapp_id] = 0
    config.user_last_bot_response_time[user_whatsapp_id] = datetime.datetime.now()
    config.user_in_training_mode[user_whatsapp_id] = False
    config.user_photo_analysis_count[user_whatsapp_id] = 0
    config.user_in_human_takeover_mode[user_whatsapp_id] = False

    # FIX: Use .get() to properly check for existing gender value
    # This preserves gender that was set from API in process_parsed_message
    existing_gender = config.user_gender.get(user_whatsapp_id)
    if existing_gender and existing_gender in ["male", "female"]:
        config.user_greeting_stage[user_whatsapp_id] = 2  # Skip gender question
        print(f"✅ Gender already set (preserving): {existing_gender}")
    else:
        config.user_gender[user_whatsapp_id] = "unknown"  # Use "unknown" for consistency
        config.user_greeting_stage[user_whatsapp_id] = 1  # Ask for gender
        print("ℹ️ Gender not found, will ask user")

    if user_whatsapp_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_whatsapp_id] = {}

    config.user_data_whatsapp[user_whatsapp_id]["user_preferred_lang"] = "ar"
    config.user_data_whatsapp[user_whatsapp_id]["initial_user_query_to_process"] = None
    config.user_data_whatsapp[user_whatsapp_id]["awaiting_human_handover_confirmation"] = False
    config.user_data_whatsapp[user_whatsapp_id]["current_conversation_id"] = None

    initial_message = config.WELCOME_MESSAGES.get(
        config.user_data_whatsapp[user_whatsapp_id]["user_preferred_lang"], config.WELCOME_MESSAGES["ar"]
    )

    # Use current provider's adapter (MontyMobile/Meta/etc.) - not hardcoded Meta
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)
    await adapter.send_text_message(user_whatsapp_id, initial_message)

    # NOTE: Removed call to start_command() to prevent:
    # 1. Duplicate welcome messages
    # 2. Potential gender reset
    # All initialization is now done in this function

    print(
        f"DEBUG: start_command_whatsapp ended for user {user_whatsapp_id}. Stage: {config.user_greeting_stage[user_whatsapp_id]}, Gender: '{config.user_gender.get(user_whatsapp_id, 'unknown')}'"
    )

