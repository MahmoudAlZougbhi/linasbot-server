"""Core _process_and_respond phase 1."""
from __future__ import annotations

import asyncio
import time

import config
from services.analytics_events import analytics

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase1(ctx: dict):
    get_canonical_user_id_and_phone = ctx.get('get_canonical_user_id_and_phone')
    get_dynamic_message = ctx.get('get_dynamic_message')
    get_firestore_db = ctx.get('get_firestore_db')
    is_flow_logging_enabled = ctx.get('is_flow_logging_enabled')
    language_detection_service = ctx.get('language_detection_service')
    log_interaction = ctx.get('log_interaction')
    save_conversation_message_to_firestore = ctx.get('save_conversation_message_to_firestore')
    send_action_func = ctx.get('send_action_func')
    send_message_func = ctx.get('send_message_func')
    takeover_check_error = ctx.get('takeover_check_error')
    user_data = ctx.get('user_data')
    user_id = ctx.get('user_id')
    user_image_base64 = ctx.get('user_image_base64')
    user_image_format = ctx.get('user_image_format')
    user_input_to_process = ctx.get('user_input_to_process')
    user_name = ctx.get('user_name')
    user_persistence = ctx.get('user_persistence')
    """
    Core logic for processing user input and generating bot response.
    This function is adapted from the original `_process_and_respond`
    but now works with WhatsApp IDs and sender functions.
    """
    from utils.utils import is_post_takeover_escalation_cooldown, set_post_takeover_escalation_cooldown

    # Start timing for response time tracking
    start_time = time.time()
    _dynamic_retrieval_flow_meta = None  # Set when dynamic retrieval is used (for Activity Flow)

    if user_image_base64:
        from services.ai_limits_enforcement import customer_image_limit_message, enforce_image_analysis_quota

        image_quota = enforce_image_analysis_quota(user_id=user_id, user_data=user_data, amount=1, consume=True)
        if not image_quota.allowed:
            limit_msg = customer_image_limit_message(image_quota)
            await send_message_func(user_id, limit_msg)
            try:
                if is_flow_logging_enabled():
                    log_interaction(
                        user_id,
                        user_input_to_process or "[صورة]",
                        limit_msg,
                        "rate_limit",
                        user_name=user_name,
                        user_data=user_data,
                        message_type="image",
                        outcome="ai_image_limit",
                        ai_called=False,
                        cost_status="none",
                    )
            except Exception:
                pass
            return _PHASE_HALT

    current_gender = config.user_gender.get(user_id, "unknown")
    current_preferred_lang = user_data.get("user_preferred_lang", "ar")
    current_conversation_id = user_data.get("current_conversation_id")
    firestore_conversation_id = str(current_conversation_id or "")

    # ===== PRE-GPT LANGUAGE DETECTION =====
    is_expecting_name = user_data.get("awaiting_name_input", False)
    lang_result = language_detection_service.detect_language(
        user_id=user_id, message=user_input_to_process, user_data=user_data, is_expecting_name=is_expecting_name
    )

    # Update language variables
    current_preferred_lang = lang_result["detected_language"]
    response_language = lang_result["response_language"]
    # Customer reply language is CM Languages policy only (not app Settings / owner profile).
    from services.cm.constants import DEFAULT_TENANT_ID as _LANG_DEFAULT_TENANT
    from services.cm.language_policy import resolve_customer_response_language

    _lang_tenant = str(user_data.get("tenant_id") or _LANG_DEFAULT_TENANT).strip() or _LANG_DEFAULT_TENANT
    response_language = resolve_customer_response_language(
        tenant_id=_lang_tenant,
        detected_language=current_preferred_lang,
    )
    router_reply_lang = response_language if response_language in ("ar", "en", "fr") else current_preferred_lang

    print(f"[_process_and_respond] 🌐 Language detected: {current_preferred_lang} → respond in: {response_language}")
    # =====================================

    # Instagram/Facebook never create or manage appointments inside the social DM.
    # Laser-specific branch/gender WhatsApp routing is legacy-bridge only.
    # Published CM tenants use the CM handoff pipeline (no Beirut/Antelias leakage).
    from services.cm.constants import (
        DEFAULT_TENANT_ID as _CM_DEFAULT_TENANT,
    )
    from services.cm.constants import (
        tenant_allows_legacy_bridge as _tenant_allows_legacy_bridge,
    )
    from services.cm.constants import (
        tenant_uses_cm_runtime as _tenant_uses_cm_runtime,
    )
    from services.social_contact_routing import (
        clear_social_booking_preference,
        is_social_channel,
        route_social_contact_request,
        social_booking_preference_key,
        social_booking_preference_reply,
    )

    if is_social_channel(user_data.get("channel")):
        _social_tenant = user_data.get("tenant_id") or _CM_DEFAULT_TENANT
        _use_legacy_social_router = _tenant_allows_legacy_bridge(_social_tenant) and not _tenant_uses_cm_runtime(
            _social_tenant
        )
        if _use_legacy_social_router:
            if user_data.get("user_preferred_lang") != current_preferred_lang:
                user_persistence.save_user_language(user_id, current_preferred_lang)
            social_route = route_social_contact_request(
                user_input_to_process,
                user_data,
                current_preferred_lang,
            )
            if social_route:
                preference_persisted = True
                if social_route.preference_to_persist:
                    preference_persisted = await user_persistence.save_social_booking_preference(
                        user_id,
                        social_booking_preference_key(user_data),
                        social_route.preference_to_persist,
                    )
                    if not preference_persisted:
                        clear_social_booking_preference(user_data)

                reply = social_route.reply
                if social_route.intent == "preference" and social_route.gender in {"male", "female"}:
                    reply = social_booking_preference_reply(
                        current_preferred_lang,
                        social_route.gender,
                        persisted=preference_persisted,
                    )

                await send_message_func(user_id, reply)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    reply,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={
                        "handled_by": "deterministic_social_router",
                        "channel": user_data.get("channel"),
                        "social_contact_intent": social_route.intent,
                        "social_contact_env": social_route.contact_env,
                        "social_preference_persisted": preference_persisted,
                    },
                )
                return _PHASE_HALT

    # DEBUG: Log gender state at start of processing
    print(f"[_process_and_respond] 🔍 USER STATE for ...{str(user_id)[-4:]}:")
    print(f"   - current_gender: '{current_gender}'")
    print(f"   - greeting_stage: {config.user_greeting_stage.get(user_id, 0)}")
    print(f"   - gender_attempts: {config.gender_attempts.get(user_id, 0)}")

    # 📊 ANALYTICS: Log user's message
    analytics.log_message(
        source="user",
        msg_type="text",
        user_id=user_id,
        language=current_preferred_lang,
        message_length=len(user_input_to_process),
    )

    # AI-PRIMARY: Bot passes message to AI as-is. AI extracts language, gender, name and returns them.
    # Bot saves what AI returns. No bot-side keyword/pattern extraction for name.

    # Check if human takeover is active (dashboard /api/test-* sets _dashboard_test_simulation to bypass and reach GPT)
    if not user_data.get("_dashboard_test_simulation") and config.user_in_human_takeover_mode.get(user_id, False):
        print(
            f"[_process_and_respond] INFO: Conversation {current_conversation_id} for user {user_id} is in human takeover mode. AI fallback guard active."
        )
        # IMPORTANT: During assigned operator takeover, AI must stay silent.
        # We only stay silent when an operator is assigned.
        # In all uncertain/error cases, prefer sending a waiting message instead of returning no response.
        should_send_waiting = True
        takeover_still_active = True
        try:
            db = get_firestore_db()
            if db:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                users_coll = db.collection("artifacts").document("linas-ai-bot-backend").collection("users")
                candidate_user_ids = []
                for candidate in [canonical_user_id, user_id]:
                    if candidate and candidate not in candidate_user_ids:
                        candidate_user_ids.append(candidate)
                    if candidate and (candidate.startswith("+") or (candidate.isdigit() and len(candidate) >= 10)):
                        alt_candidate = candidate[1:] if candidate.startswith("+") else f"+{candidate}"
                        if alt_candidate not in candidate_user_ids:
                            candidate_user_ids.append(alt_candidate)

                conv_id_to_check = current_conversation_id
                if not conv_id_to_check:
                    from utils.utils import _resolve_latest_conversation_id

                    user_doc_ref = users_coll.document(canonical_user_id)
                    conversations_collection_for_user = user_doc_ref.collection(
                        config.FIRESTORE_CONVERSATIONS_COLLECTION
                    )
                    conv_id_to_check = await _resolve_latest_conversation_id(conversations_collection_for_user)
                    if conv_id_to_check:
                        print(
                            f"[_process_and_respond] INFO: Using latest conversation {conv_id_to_check} "
                            f"for takeover sync (no current_conversation_id)"
                        )

                conv_data = None
                if conv_id_to_check:
                    for candidate_user_id in candidate_user_ids:
                        candidate_ref = (
                            users_coll.document(candidate_user_id)
                            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                            .document(conv_id_to_check)
                        )
                        candidate_snap = await asyncio.to_thread(candidate_ref.get)
                        if candidate_snap.exists:
                            conv_data = candidate_snap.to_dict() or {}
                            break

                if conv_data is None:
                    takeover_still_active = False
                    should_send_waiting = False
                    from utils.utils import _clear_takeover_flags_for_user

                    _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                    print(
                        f"[_process_and_respond] INFO: No Firestore conversation for takeover check; "
                        f"cleared stale takeover flag for {user_id}"
                    )
                elif conv_data.get("human_takeover_active", False):
                    should_send_waiting = True
                else:
                    takeover_still_active = False
                    should_send_waiting = False
                    from utils.utils import _clear_takeover_flags_for_user, sync_post_release_cooldown_from_conv_payload

                    _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                    sync_post_release_cooldown_from_conv_payload(user_data, conv_data)
                    user_data["just_returned_from_human_takeover"] = True
                    if not is_post_takeover_escalation_cooldown(user_data):
                        set_post_takeover_escalation_cooldown(user_data)
                    print(
                        f"[_process_and_respond] INFO: Firestore shows takeover inactive for {user_id}; "
                        f"resuming normal bot flow (just_returned)."
                    )
        except Exception as takeover_check_error:
            print(f"[_process_and_respond] ⚠️ Takeover fallback check failed: {takeover_check_error}")

        if takeover_still_active and should_send_waiting:
            waiting_msg = (
                get_dynamic_message("waiting_queue_message", current_preferred_lang)
                or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
            )
            await send_message_func(user_id, waiting_msg)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                waiting_msg,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai", "source": "waiting_queue_fallback"},
            )
            return _PHASE_HALT
    _pack = ['_', '_CM_DEFAULT_TENANT', '_LANG_DEFAULT_TENANT', '_clear_takeover_flags_for_user', '_dynamic_retrieval_flow_meta', '_lang_tenant', '_resolve_latest_conversation_id', '_social_tenant', '_tenant_allows_legacy_bridge', '_tenant_uses_cm_runtime', '_use_legacy_social_router', 'alt_candidate', 'candidate', 'candidate_ref', 'candidate_snap', 'candidate_user_id', 'candidate_user_ids', 'canonical_user_id', 'clear_social_booking_preference', 'conv_data', 'conv_id_to_check', 'conversations_collection_for_user', 'current_conversation_id', 'current_gender', 'current_preferred_lang', 'customer_image_limit_message', 'db', 'enforce_image_analysis_quota', 'firestore_conversation_id', 'get_canonical_user_id_and_phone', 'get_dynamic_message', 'get_firestore_db', 'image_quota', 'is_expecting_name', 'is_flow_logging_enabled', 'is_post_takeover_escalation_cooldown', 'is_social_channel', 'lang_result', 'language_detection_service', 'limit_msg', 'log_interaction', 'preference_persisted', 'reply', 'resolve_customer_response_language', 'response_language', 'route_social_contact_request', 'router_reply_lang', 'save_conversation_message_to_firestore', 'send_action_func', 'send_message_func', 'set_post_takeover_escalation_cooldown', 'should_send_waiting', 'social_booking_preference_key', 'social_booking_preference_reply', 'social_route', 'start_time', 'sync_post_release_cooldown_from_conv_payload', 'takeover_check_error', 'takeover_still_active', 'user_data', 'user_doc_ref', 'user_id', 'user_image_base64', 'user_image_format', 'user_input_to_process', 'user_name', 'user_persistence', 'users_coll', 'waiting_msg']
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
