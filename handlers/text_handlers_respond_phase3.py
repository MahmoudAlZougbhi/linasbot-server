"""Core _process_and_respond phase 3."""
from __future__ import annotations

import datetime
from typing import Any

import config
from utils.utils import (
    get_firestore_db,
    notify_human_on_whatsapp,
)

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase3(ctx: dict):
    FALLBACK_TEMPLATES = ctx.get('FALLBACK_TEMPLATES')
    GREETING_TEMPLATES = ctx.get('GREETING_TEMPLATES')
    _activate_ai_handover_router = ctx.get('_activate_ai_handover_router')
    _build_arabic_respectful_address = ctx.get('_build_arabic_respectful_address')
    ai_primary_mode = ctx.get('ai_primary_mode')
    current_conversation_id = ctx.get('current_conversation_id')
    current_gender = ctx.get('current_gender')
    current_preferred_lang = ctx.get('current_preferred_lang')
    get_dynamic_message = ctx.get('get_dynamic_message')
    is_social_channel = ctx.get('is_social_channel')
    log_interaction = ctx.get('log_interaction')
    log_report_event = ctx.get('log_report_event')
    route_social_contact_request = ctx.get('route_social_contact_request')
    router_action = ctx.get('router_action')
    router_reply_lang = ctx.get('router_reply_lang')
    save_conversation_message_to_firestore = ctx.get('save_conversation_message_to_firestore')
    send_message_func = ctx.get('send_message_func')
    social_route = ctx.get('social_route')
    update_dashboard_metric_in_firestore = ctx.get('update_dashboard_metric_in_firestore')
    user_data = ctx.get('user_data')
    user_id = ctx.get('user_id')
    user_input_to_process = ctx.get('user_input_to_process')
    user_name = ctx.get('user_name')
    if (not ai_primary_mode) and router_action == "human_handover":
        if is_social_channel(user_data.get("channel")):
            social_route = route_social_contact_request(
                user_input_to_process,
                user_data,
                current_preferred_lang,
                force_intent="human",
            )
            if social_route:
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
                        "source": "router_human_handover_social",
                    },
                )
                return _PHASE_HALT
            # No explicit social handoff intent → skip dashboard takeover; continue to AI.
        else:

            async def _activate_ai_handover_router(escalation_reason: str, trigger_source: str) -> bool:
                from utils.utils import (
                    conversation_any_path_post_release_blocked,
                    merge_conversation_user_id_variants,
                    update_conversation_on_all_existing_paths,
                )

                wrote = False
                db = get_firestore_db()
                if db and current_conversation_id:
                    try:
                        if await conversation_any_path_post_release_blocked(current_conversation_id, user_id):
                            print("⚠️ router handover blocked: post-release cooldown on at least one path")
                            return False
                        payload: dict[str, Any] = {
                            "status": "waiting_human",
                            "human_takeover_active": True,
                            "human_takeover_requested": True,
                            "operator_id": None,
                            "conversation_state": "waiting_for_operator",
                            "escalation_reason": escalation_reason,
                            "escalation_time": datetime.datetime.now(),
                            "last_updated": datetime.datetime.now(),
                            "post_release_escalation_suppressed_until": None,
                        }
                        n = await update_conversation_on_all_existing_paths(current_conversation_id, user_id, payload)
                        if n > 0:
                            wrote = True
                    except Exception as e:
                        print(f"⚠️ Failed to update handover state: {e}")
                if not wrote:
                    return False
                for vid in merge_conversation_user_id_variants("", user_id):
                    config.user_in_human_takeover_mode[vid] = True
                notify_human_on_whatsapp(
                    user_name,
                    current_gender,
                    user_input_to_process,
                    type_of_notification=f"AI handover - {escalation_reason}",
                )
                try:
                    from services.human_takeover_notification_service import human_takeover_notification_service

                    await human_takeover_notification_service.notify_and_audit_handoff(
                        user_id=user_id,
                        user_gender=current_gender,
                        customer_name=user_name,
                        customer_phone=user_data.get("phone_number", "Unknown"),
                        escalation_reason=escalation_reason,
                        last_message=user_input_to_process,
                        trigger_source=trigger_source,
                        conversation_id=current_conversation_id,
                        tenant_id=user_data.get("tenant_id") or user_data.get("tenantId"),
                        channel=user_data.get("channel"),
                        extra_details={"action": "router_human_handover"},
                    )
                except Exception as notify_error:
                    print(f"⚠️ Failed to send handoff: {notify_error}")
                return True

            router_handover_ok = await _activate_ai_handover_router("customer_requested_human", "router_human_handover")
            if router_handover_ok:
                handoff_msgs = {
                    "ar": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏",
                    "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏",
                    "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏",
                }
                router_sent_reply = handoff_msgs.get(current_preferred_lang, handoff_msgs["ar"])
                await send_message_func(user_id, router_sent_reply)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    router_sent_reply,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={"handled_by": "ai"},
                )
                log_report_event(
                    "human_handover",
                    user_id,
                    current_gender,
                    {"message": user_input_to_process, "status": "router_direct", "source": "router"},
                )
                await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
            else:
                fb = get_dynamic_message("generic_error_message", current_preferred_lang) or "كيف فيني ساعدك؟"
                await send_message_func(user_id, fb)
                await save_conversation_message_to_firestore(
                    user_id,
                    "ai",
                    fb,
                    current_conversation_id,
                    user_name,
                    user_data.get("phone_number"),
                    metadata={"handled_by": "ai"},
                )
            return _PHASE_HALT

    # 2. Greeting only (Phase 7)
    if (not ai_primary_mode) and router_action == "greeting":
        if router_reply_lang in ("ar", "franco"):
            respectful_address = _build_arabic_respectful_address(current_gender, user_name)
            greeting_msg = f"مرحباً {respectful_address}، أنا مروى، المساعد الذكي في ليناز ليزر. كيف فيني ساعدك؟"
        else:
            greeting_msg = get_dynamic_message("router_greeting", router_reply_lang) or GREETING_TEMPLATES.get(
                router_reply_lang, GREETING_TEMPLATES["ar"]
            )
        await send_message_func(user_id, greeting_msg)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            greeting_msg,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "source": "router_greeting"},
        )
        log_interaction(
            user_id,
            user_input_to_process,
            greeting_msg,
            "router_greeting",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="router_greeting",
            outcome="greeting",
            ai_called=False,
            cost_status="none",
        )
        return _PHASE_HALT

    # 3. Fallback (Phase 11)
    if (not ai_primary_mode) and router_action == "fallback":
        fallback_msg = get_dynamic_message("router_fallback", router_reply_lang) or FALLBACK_TEMPLATES.get(
            router_reply_lang, FALLBACK_TEMPLATES["ar"]
        )
        await send_message_func(user_id, fallback_msg)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            fallback_msg,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "source": "router_fallback"},
        )
        log_interaction(
            user_id,
            user_input_to_process,
            fallback_msg,
            "router_fallback",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="router_fallback",
            outcome="fallback",
            ai_called=False,
            cost_status="none",
        )
        return _PHASE_HALT

    # 4. Ask gender (Phase 8)
    if (not ai_primary_mode) and router_action == "ask_gender":
        user_data["original_question"] = user_input_to_process
        user_data["awaiting_gender"] = True
        user_data["last_bot_question_type"] = "gender"
        user_data["initial_user_query_to_process"] = user_input_to_process  # backward compat
        gender_questions = config.GENDER_QUESTIONS.get(router_reply_lang, config.GENDER_QUESTIONS["ar"])
        import random

        gender_msg = random.choice(gender_questions)
        await send_message_func(user_id, gender_msg)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            gender_msg,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "source": "router_ask_gender"},
        )
        log_interaction(
            user_id,
            user_input_to_process,
            gender_msg,
            "router_ask_gender",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="router_ask_gender",
            outcome="ask_gender",
            ai_called=False,
            cost_status="none",
        )
        return _PHASE_HALT
    _pack = ['FALLBACK_TEMPLATES', 'GREETING_TEMPLATES', '_activate_ai_handover_router', '_build_arabic_respectful_address', 'ai_primary_mode', 'current_conversation_id', 'current_gender', 'current_preferred_lang', 'fallback_msg', 'fb', 'gender_msg', 'gender_questions', 'get_dynamic_message', 'greeting_msg', 'handoff_msgs', 'is_social_channel', 'log_interaction', 'log_report_event', 'random', 'respectful_address', 'route_social_contact_request', 'router_action', 'router_handover_ok', 'router_reply_lang', 'router_sent_reply', 'save_conversation_message_to_firestore', 'send_message_func', 'social_route', 'update_dashboard_metric_in_firestore', 'user_data', 'user_id', 'user_input_to_process', 'user_name']
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
