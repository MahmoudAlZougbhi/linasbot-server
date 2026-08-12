from __future__ import annotations

# handlers/text_handlers_message.py
# Main message handler for WhatsApp text messages
# Human handoff: AI detects intent (no keyword/regex - AI understands context)
import asyncio
import datetime
from collections import deque
from typing import Any

import config
from handlers.text_handlers_delayed import _delayed_process_messages
from handlers.text_handlers_firestore import _delayed_processing_tasks
from handlers.text_handlers_message_greeting import (
    GREETING_INACTIVITY_SECONDS,
    _combine_schedule_lock,
    _get_session_greeting_message,
)
from handlers.text_handlers_message_takeover import (
    maybe_send_takeover_autoreply,
    resolve_conversation_doc_ref,
)
from handlers.training_handlers import handle_training_input
from services.outbound_turn_idempotency import record_inbound_mid_for_ai_turn
from services.sentiment_escalation_service import sentiment_service
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
    save_conversation_message_to_firestore,
)


async def handle_message(
    user_id: str,
    user_name: str,
    user_input_text: str,
    user_data: dict,
    send_message_func: Any,
    send_action_func: Any,
    skip_firestore_save: bool = False,
    message_combine_delay: float | None = None,
) -> Any:
    """
    Main message handler for WhatsApp text messages.
    Combines rapid messages and then processes them.

    Args:
        skip_firestore_save: If True, skips saving to Firestore (used when called from voice_handlers after already saving)
        message_combine_delay: If set (e.g. 0.0), overrides config.MESSAGE_COMBINING_DELAY for this turn (dashboard tests).
    """
    user_id = str(user_id).strip()
    config.user_names[user_id] = user_name

    # Ensure defaultdicts are initialized for this user
    if user_id not in config.user_context:
        config.user_context[user_id] = deque(maxlen=config.MAX_CONTEXT_MESSAGES)
    if user_id not in config.user_pending_messages:
        config.user_pending_messages[user_id] = deque()
    if user_id not in config.user_last_bot_response_time:
        config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    if user_id not in config.user_greeting_stage:
        config.user_greeting_stage[user_id] = 0
    # FIX: Only set to "unknown" if gender is not already a valid value
    # This prevents overwriting gender restored from Firestore after restart
    current_gender = config.user_gender.get(user_id)
    if current_gender not in ["male", "female"]:
        config.user_gender[user_id] = "unknown"
    if user_id not in config.gender_attempts:
        config.gender_attempts[user_id] = 0
    if user_id not in config.user_in_training_mode:
        config.user_in_training_mode[user_id] = False
    if user_id not in config.user_photo_analysis_count:
        config.user_photo_analysis_count[user_id] = 0
    if user_id not in config.user_in_human_takeover_mode:
        config.user_in_human_takeover_mode[user_id] = False

    # Check if user is in training mode
    if config.user_in_training_mode.get(user_id, False):
        print(
            f"[handle_message] INFO: User ...{str(user_id)[-4:]} in training mode. Handing over to handle_training_input."
        )
        await handle_training_input(
            user_id=user_id,
            user_input_text=user_input_text,
            user_data=user_data,
            send_message_func=send_message_func,
            send_action_func=send_action_func,
        )
        return

    raw_msg = user_input_text.strip()

    if not raw_msg:
        print(
            f"[handle_message] ERROR: No usable text in message for user ...{str(user_id)[-4:]}. raw_msg is empty. Exiting."
        )
        return

    # Per single-message guardrail: limit long pasted text to avoid excessive token usage.
    non_empty_line_count = len(
        [ln for ln in raw_msg.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    )
    if non_empty_line_count > config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE:
        await send_message_func(
            user_id,
            f"لطفاً خفّف طول الرسالة: الحد الأقصى للرسالة الواحدة هو {config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE} سطر. "
            "قسّمها على أكثر من رسالة قصيرة.",
        )
        print(
            f"[handle_message] Blocked long single message for user {user_id}: "
            f"{non_empty_line_count} lines (limit: {config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE})"
        )
        return

    # Session timing for greeting policy (new conversation or inactivity >= 1h)
    now_ts = datetime.datetime.now()
    previous_user_msg_ts = user_data.get("last_user_message_at")
    inactivity_seconds = None
    if isinstance(previous_user_msg_ts, datetime.datetime):
        inactivity_seconds = (now_ts - previous_user_msg_ts).total_seconds()
    user_data["last_user_message_at"] = now_ts

    # ✅ FIXED: Only save to Firestore if not called from voice_handlers
    # Voice handler already saved the message with type="voice" and audio_url
    if not skip_firestore_save:
        # Save user's message to Firestore immediately
        current_conversation_id = user_data.get("current_conversation_id")
        was_new_conversation = not current_conversation_id
        phone_for_save = user_data.get("phone_number")

        source_message_id = user_data.pop("_source_message_id", None)
        message_metadata = {"type": "text"}
        channel = str(user_data.get("channel") or "").strip().lower()
        if channel:
            message_metadata["channel"] = channel
        if source_message_id:
            message_metadata["source_message_id"] = source_message_id
        record_inbound_mid_for_ai_turn(user_data, source_message_id)

        await save_conversation_message_to_firestore(
            user_id,
            "user",
            raw_msg,
            current_conversation_id,
            user_name,
            phone_for_save,
            metadata=message_metadata,
        )

        # Update local user_data with the conversation_id (might have been created)
        # Save uses canonical_user_id; we must read from both so context is available for GPT.
        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, phone_for_save)
        new_conv_id = config.user_data_whatsapp.get(user_id, {}).get(
            "current_conversation_id"
        ) or config.user_data_whatsapp.get(canonical_user_id, {}).get("current_conversation_id")
        if new_conv_id:
            if user_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_id] = {}
            config.user_data_whatsapp[user_id]["current_conversation_id"] = new_conv_id
        print(f"📍 After save: conversation_id is now: {new_conv_id}")
        user_data["current_conversation_id"] = new_conv_id
    else:
        print(
            "[handle_message] INFO: Skipping Firestore save (called from voice_handler with skip_firestore_save=True)"
        )
        # Just ensure current_conversation_id is up-to-date (check both user_id and canonical)
        if "current_conversation_id" not in user_data or not user_data["current_conversation_id"]:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            user_data["current_conversation_id"] = config.user_data_whatsapp.get(user_id, {}).get(
                "current_conversation_id"
            ) or config.user_data_whatsapp.get(canonical_user_id, {}).get("current_conversation_id")
        was_new_conversation = not user_data.get("current_conversation_id")

    current_conversation_id = user_data.get("current_conversation_id")

    # Session-level greeting eligibility for this turn:
    # allowed only for truly new conversation or inactivity >= 12 hours.
    user_data["_greeting_eligible_this_turn"] = bool(
        was_new_conversation or (inactivity_seconds is not None and inactivity_seconds >= GREETING_INACTIVITY_SECONDS)
    )

    # Get Firestore DB instance for sentiment and takeover checks
    db = get_firestore_db()

    # AI-primary: GPT decides when to transfer to human (handover_degree, human_handover action).
    # Sentiment is still logged for dashboard; escalation decision is delegated to GPT.
    # Owner alerts for anger/offensive use this same keyword analyzer (no new ML).
    sentiment_analysis = sentiment_service.analyze_sentiment(
        user_id=user_id, message=raw_msg, language=user_data.get("user_preferred_lang", "ar")
    )

    try:
        from services.owner_alert_service import owner_alert_service

        owner_alert_service.emit_sentiment_signal(
            tenant_id=user_data.get("tenant_id") or user_data.get("tenantId"),
            customer_name=user_name,
            user_id=user_id,
            conversation_id=user_data.get("current_conversation_id"),
            channel=user_data.get("channel"),
            sentiment_analysis=sentiment_analysis,
            last_message=raw_msg,
        )
    except Exception as alert_err:
        print(f"⚠️ Failed to persist sentiment owner alert: {alert_err}")

    # Update conversation sentiment in Firebase (for dashboard/analytics only)
    if db and user_data.get("current_conversation_id"):
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
            conv_doc_ref, doc_snap, _ = await resolve_conversation_doc_ref(
                users_coll,
                user_data["current_conversation_id"],
                canonical_user_id,
                user_id,
            )
            if not doc_snap or not doc_snap.exists:
                raise ValueError("Conversation not found for sentiment update")
            await asyncio.to_thread(
                conv_doc_ref.update,
                {"sentiment": sentiment_analysis["sentiment"], "last_updated": datetime.datetime.now()},
            )
            print(f"✅ Updated conversation sentiment to: {sentiment_analysis['sentiment']}")
        except Exception as e:
            print(f"⚠️ Failed to update sentiment in Firebase: {e}")

    if await maybe_send_takeover_autoreply(
        db=db,
        user_id=user_id,
        user_name=user_name,
        user_data=user_data,
        send_message_func=send_message_func,
    ):
        return

    ai_primary_mode = bool(getattr(config, "AI_PRIMARY_ORCHESTRATION", True))

    # Greeting policy (code-driven) runs only in non AI-primary mode.
    # In AI-primary mode, greeting timing/wording decisions are delegated to AI.
    if not ai_primary_mode:
        # Greeting policy:
        # - New conversation => send greeting first
        # - Existing conversation but user inactive >= threshold => send greeting first
        greeting_sent_for_conv = user_data.get("greeting_sent_for_conversation_id")
        should_greet_now = False
        if current_conversation_id and greeting_sent_for_conv != current_conversation_id:
            if was_new_conversation:
                should_greet_now = True
            elif inactivity_seconds is not None and inactivity_seconds >= GREETING_INACTIVITY_SECONDS:
                should_greet_now = True

        if should_greet_now:
            user_lang = user_data.get("user_preferred_lang", "ar")
            greeting_msg = _get_session_greeting_message(user_lang)
            await send_message_func(user_id, greeting_msg)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                greeting_msg,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai", "source": "session_greeting"},
            )
            user_data["greeting_sent_for_conversation_id"] = current_conversation_id

    # Check if it's the very first message after start
    if config.user_greeting_stage[user_id] == 1 and not config.user_gender.get(user_id):
        common_greetings_only = [
            "hi",
            "hello",
            "مرحبا",
            "سلام",
            "اهلين",
            "صباح الخير",
            "مساء الخير",
            "كيفك",
            "كيف الحال",
            "kifak",
            "shu",
            "bonjour",
            "salut",
            "bade",
            "sheel",
            "shil",
            "ana",
            "ta3ite",
        ]
        is_only_greeting = any(g == raw_msg.lower().strip() for g in common_greetings_only)

        if not is_only_greeting:
            if user_data["initial_user_query_to_process"] is None:
                user_data["initial_user_query_to_process"] = raw_msg
        else:
            user_data["initial_user_query_to_process"] = None

    # Language detection is now handled BEFORE GPT call by language_detection_service
    # The LanguageResolver detects language on each message using heuristics (Arabic script, Franco-Arabic, French/English markers)
    # GPT is then instructed to respond in the detected language
    print(
        f"[handle_message] 🌐 Language will be detected pre-GPT by language_detection_service for user ...{str(user_id)[-4:]}"
    )

    async with _combine_schedule_lock(user_id):
        # Message combining logic
        config.user_pending_messages[user_id].append(raw_msg)
        # Dashboard /api/test-*: if a webhook-delayed task for this user was just cancelled, it may have
        # left the pending deque empty; keep a copy so _delayed_process_messages can still run GPT.
        if user_data.get("_dashboard_test_simulation"):
            user_data["_dashboard_last_message_for_fallback"] = raw_msg
            # Survives pending-queue races (e.g. cancelled delayed task cleared deque); cleared in delayed after GPT turn.
            user_data["_dashboard_test_turn_sticky"] = raw_msg

        # Cancel any previously scheduled processing task
        if user_id in _delayed_processing_tasks and not _delayed_processing_tasks[user_id].done():
            _delayed_processing_tasks[user_id].cancel()

        # New epoch for this combine/GPT wave. A previously cancelled task may still finish GPT and
        # try to send; outbound uses this so stale turns skip WhatsApp delivery (duplicate bubble fix).
        user_data["_text_turn_epoch"] = user_data.get("_text_turn_epoch", 0) + 1
        text_turn_epoch = user_data["_text_turn_epoch"]

        # Dashboard /api/test-* sets _dashboard_test_simulation: run GPT path inline so the HTTP handler
        # sees captured replies before returning (background create_task was still racing / missing awaits).
        if user_data.get("_dashboard_test_simulation"):
            print(f"[handle_message] Dashboard test simulation: inline delayed processing for ...{str(user_id)[-4:]}")
            try:
                await _delayed_process_messages(
                    user_id,
                    user_data,
                    send_message_func,
                    send_action_func,
                    combine_delay_seconds=message_combine_delay,
                    text_turn_epoch=text_turn_epoch,
                )
            finally:
                _delayed_processing_tasks.pop(user_id, None)
            return

        _delayed_processing_tasks[user_id] = asyncio.create_task(
            _delayed_process_messages(
                user_id,
                user_data,
                send_message_func,
                send_action_func,
                combine_delay_seconds=message_combine_delay,
                text_turn_epoch=text_turn_epoch,
            )
        )
