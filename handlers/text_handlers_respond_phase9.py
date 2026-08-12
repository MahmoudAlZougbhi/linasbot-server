"""Core _process_and_respond phase 9."""
from __future__ import annotations

import config

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase9(ctx: dict):
    _activate_ai_handover = ctx.get('_activate_ai_handover')
    action = ctx.get('action')
    bot_reply_text = ctx.get('bot_reply_text')
    current_conversation_id = ctx.get('current_conversation_id')
    current_gender = ctx.get('current_gender')
    current_preferred_lang = ctx.get('current_preferred_lang')
    detected_gender_from_gpt = ctx.get('detected_gender_from_gpt')
    escalation_reason_from_gpt = ctx.get('escalation_reason_from_gpt')
    flow_meta = ctx.get('flow_meta')
    get_dynamic_message = ctx.get('get_dynamic_message')
    is_social_channel = ctx.get('is_social_channel')
    log_report_event = ctx.get('log_report_event')
    route_social_contact_request = ctx.get('route_social_contact_request')
    save_conversation_message_to_firestore = ctx.get('save_conversation_message_to_firestore')
    send_message_func = ctx.get('send_message_func')
    sent_reply = ctx.get('sent_reply')
    social_route = ctx.get('social_route')
    update_dashboard_metric_in_firestore = ctx.get('update_dashboard_metric_in_firestore')
    user_data = ctx.get('user_data')
    user_id = ctx.get('user_id')
    user_input_to_process = ctx.get('user_input_to_process')
    user_name = ctx.get('user_name')
    user_persistence = ctx.get('user_persistence')
    if action in ["initial_greet_and_ask_gender", "ask_gender"]:
        # AI-primary: AI decides to request gender, backend persists state and executes.
        if not user_data.get("original_question"):
            user_data["original_question"] = user_input_to_process
        user_data["awaiting_gender"] = True
        user_data["awaiting_clarification"] = False
        user_data["last_bot_question_type"] = "gender"
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )

    elif action == "confirm_gender":
        # AI-primary: AI confirmed gender and decided the wording.
        if detected_gender_from_gpt and detected_gender_from_gpt in ["male", "female"]:
            await user_persistence.save_user_gender(
                user_id, detected_gender_from_gpt, phone=user_data.get("phone_number", user_id), name=user_name
            )
            print(f"✅ Saved gender '{detected_gender_from_gpt}' for user ...{str(user_id)[-4:]} to API")
        user_data["awaiting_gender"] = False
        user_data["last_bot_question_type"] = None
        config.user_greeting_stage[user_id] = 2
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )

    elif action == "confirm_booking_details":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )
        config.user_greeting_stage[user_id] = 2

    elif action == "human_handover_initial_ask":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )
        user_data["awaiting_human_handover_confirmation"] = True

    elif action == "human_handover_confirmed":
        user_data["awaiting_human_handover_confirmation"] = False
        handover_ok = await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "customer_requested_human",
            trigger_source="ai_handover_confirmed",
        )
        if handover_ok:
            handoff_msg = (
                get_dynamic_message("human_handover_message", current_preferred_lang)
                or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
            )
            sent_reply = handoff_msg
            await send_message_func(user_id, handoff_msg)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                handoff_msg,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai"},
            )
            log_report_event(
                "human_handover",
                user_id,
                current_gender,
                {"message": user_input_to_process, "status": "confirmed", "source": "ai_handover_confirmed"},
            )
            await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        else:
            fallback = (bot_reply_text or "").strip() or (
                get_dynamic_message("generic_error_message", current_preferred_lang) or "تمام، كيف فيني ساعدك بهاللحظة؟"
            )
            sent_reply = fallback
            await send_message_func(user_id, fallback)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                fallback,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai"},
            )

    elif action == "return_to_normal_chat":
        user_data["awaiting_human_handover_confirmation"] = False
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )

    elif action == "human_handover":
        handover_ok = await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "ai_decided_handoff", trigger_source="ai_handover_direct"
        )
        if handover_ok:
            handoff_msg = (
                get_dynamic_message("human_handover_message", current_preferred_lang)
                or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
            )
            sent_reply = handoff_msg
            await send_message_func(user_id, handoff_msg)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                sent_reply,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai"},
            )
            log_report_event(
                "human_handover",
                user_id,
                current_gender,
                {"message": user_input_to_process, "status": "direct", "source": "ai_handover_direct"},
            )
            await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        else:
            fallback = (bot_reply_text or "").strip() or (
                get_dynamic_message("generic_error_message", current_preferred_lang) or "كيف فيني ساعدك بهاللحظة؟"
            )
            sent_reply = fallback
            await send_message_func(user_id, fallback)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                fallback,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai"},
            )

    elif action in [
        "ask_for_details_for_booking",
        "ask_for_service_type",
        "ask_for_details",
        "ask_for_tattoo_photo",
        "ask_clarification",
    ]:
        # Clarification anchor should point to the question being clarified now.
        # If we're already awaiting clarification, keep the existing anchor.
        clarification_anchor = (
            user_data.get("pending_clarification_query") if user_data.get("awaiting_clarification") else None
        )
        if not clarification_anchor:
            clarification_anchor = user_data.get("original_question") or user_input_to_process
        user_data["original_question"] = clarification_anchor
        user_data["awaiting_clarification"] = True
        user_data["last_bot_question_type"] = "clarification"
        user_data["pending_clarification_query"] = clarification_anchor
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )
        config.user_greeting_stage[user_id] = 2

    elif action in ["content_moderated", "rate_limit_exceeded"]:
        # Moderation or rate limit: send the safe/limit message from the service (no GPT call).
        user_data["awaiting_gender"] = False
        user_data["awaiting_clarification"] = False
        user_data["pending_clarification_query"] = None
        reply_to_send = (bot_reply_text or "").strip() or (
            get_dynamic_message("generic_error_message", current_preferred_lang)
            or "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى."
        )
        sent_reply = reply_to_send
        await send_message_func(user_id, reply_to_send)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            reply_to_send,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "action": action},
        )
        config.user_greeting_stage[user_id] = 2

    elif action in [
        "answer_question",
        "normal_chat",
        "unknown_query",
        "provide_info",
        "tool_call",
        "check_customer_status",
        "confirm_appointment_reschedule",
    ]:
        user_data["awaiting_gender"] = False
        user_data["awaiting_clarification"] = False
        user_data["pending_clarification_query"] = None
        # Clear stale carry-over so the next user intent starts fresh.
        user_data["original_question"] = None
        user_data["initial_user_query_to_process"] = None
        user_data["last_bot_question_type"] = None
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            bot_reply_text,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai"},
        )
        config.user_greeting_stage[user_id] = 2

    else:
        # Unexpected action → hand over to human instead of generic error
        # Social DMs never enter dashboard takeover; route to WhatsApp contact instead.
        if is_social_channel(user_data.get("channel")):
            social_route = route_social_contact_request(
                user_input_to_process,
                user_data,
                current_preferred_lang,
                force_intent="human",
            )
            if social_route:
                sent_reply = social_route.reply
                await send_message_func(user_id, social_route.reply)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    social_route.reply,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={
                        "handled_by": "deterministic_social_router",
                        "channel": user_data.get("channel"),
                        "social_contact_intent": social_route.intent,
                        "social_contact_env": social_route.contact_env,
                        "source": "unexpected_action_social",
                    },
                )
            else:
                fallback = (bot_reply_text or "").strip() or (
                    get_dynamic_message("generic_error_message", current_preferred_lang)
                    or "عذراً، صار خطأ بسيط. جرّب توضّح طلبك مرة ثانية."
                )
                sent_reply = fallback
                await send_message_func(user_id, fallback)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    fallback,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={"handled_by": "ai", "channel": user_data.get("channel")},
                )
        else:
            _flow_error_reason = f"Step: Bot → User | Unexpected action: '{action}'"
            print(
                f"[_process_and_respond] ERROR: Unexpected action '{action}' → handing over to human. bot_reply_len={len(bot_reply_text or '')} | flow_error={flow_meta.get('error', 'none')}"
            )
            handover_ok = await _activate_ai_handover(
                escalation_reason=escalation_reason_from_gpt or "technical_error", trigger_source="unexpected_action"
            )
            if handover_ok:
                handoff_msg = (
                    get_dynamic_message("human_handover_message", current_preferred_lang)
                    or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
                )
                sent_reply = handoff_msg
                await send_message_func(user_id, handoff_msg)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    sent_reply,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={"handled_by": "ai"},
                )
                log_report_event(
                    "human_handover",
                    user_id,
                    current_gender,
                    {"message": user_input_to_process, "status": "direct", "source": "unexpected_action"},
                )
                await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
            else:
                fallback = (bot_reply_text or "").strip() or (
                    get_dynamic_message("generic_error_message", current_preferred_lang)
                    or "عذراً، صار خطأ بسيط. جرّب توضّح طلبك مرة ثانية."
                )
                sent_reply = fallback
                await send_message_func(user_id, fallback)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    fallback,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={"handled_by": "ai"},
                )
    _pack = ['_activate_ai_handover', '_flow_error_reason', 'action', 'bot_reply_text', 'clarification_anchor', 'current_conversation_id', 'current_gender', 'current_preferred_lang', 'detected_gender_from_gpt', 'escalation_reason_from_gpt', 'fallback', 'flow_meta', 'get_dynamic_message', 'handoff_msg', 'handover_ok', 'is_social_channel', 'log_report_event', 'reply_to_send', 'route_social_contact_request', 'save_conversation_message_to_firestore', 'send_message_func', 'sent_reply', 'social_route', 'update_dashboard_metric_in_firestore', 'user_data', 'user_id', 'user_input_to_process', 'user_name', 'user_persistence']
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
