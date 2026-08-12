"""Core _process_and_respond phase 4."""

from __future__ import annotations

from typing import Any, cast

import config

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase4(ctx: dict) -> Any:
    ASK_CLARIFICATION_TEMPLATES = cast(Any, ctx.get("ASK_CLARIFICATION_TEMPLATES"))
    _build_booking_decline_reply = cast(Any, ctx.get("_build_booking_decline_reply"))
    _classify_booking_offer_confirmation_reply = cast(Any, ctx.get("_classify_booking_offer_confirmation_reply"))
    ai_primary_mode = cast(Any, ctx.get("ai_primary_mode"))
    canonical_user_id = cast(Any, ctx.get("canonical_user_id"))
    conv_state = cast(Any, ctx.get("conv_state"))
    current_conversation_id = cast(Any, ctx.get("current_conversation_id"))
    current_gender = cast(Any, ctx.get("current_gender"))
    current_preferred_lang = cast(Any, ctx.get("current_preferred_lang"))
    firestore_conversation_id = cast(Any, ctx.get("firestore_conversation_id"))
    get_bot_chat_response = cast(Any, ctx.get("get_bot_chat_response"))
    get_canonical_user_id_and_phone = cast(Any, ctx.get("get_canonical_user_id_and_phone"))
    get_conversation_context_for_gpt = cast(Any, ctx.get("get_conversation_context_for_gpt"))
    get_conversation_last_ai_response_at = cast(Any, ctx.get("get_conversation_last_ai_response_at"))
    get_dynamic_message = cast(Any, ctx.get("get_dynamic_message"))
    get_gender_from_message = cast(Any, ctx.get("get_gender_from_message"))
    log_interaction = cast(Any, ctx.get("log_interaction"))
    response_language = cast(Any, ctx.get("response_language"))
    router_action = cast(Any, ctx.get("router_action"))
    router_reply_lang = cast(Any, ctx.get("router_reply_lang"))
    save_conversation_message_to_firestore = cast(Any, ctx.get("save_conversation_message_to_firestore"))
    send_message_func = cast(Any, ctx.get("send_message_func"))
    user_data = cast(Any, ctx.get("user_data"))
    user_id = cast(Any, ctx.get("user_id"))
    user_input_to_process = cast(Any, ctx.get("user_input_to_process"))
    user_name = cast(Any, ctx.get("user_name"))
    user_persistence = cast(Any, ctx.get("user_persistence"))
    if (not ai_primary_mode) and router_action == "ask_clarification":
        user_data["original_question"] = user_input_to_process
        user_data["awaiting_clarification"] = True
        user_data["last_bot_question_type"] = "clarification"
        user_data["pending_clarification_query"] = user_input_to_process  # backward compat
        clarification_msg = get_dynamic_message(
            "router_ask_clarification", router_reply_lang
        ) or ASK_CLARIFICATION_TEMPLATES.get(router_reply_lang, ASK_CLARIFICATION_TEMPLATES["ar"])
        await send_message_func(user_id, clarification_msg)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            clarification_msg,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "source": "router_ask_clarification"},
        )
        log_interaction(
            user_id,
            user_input_to_process,
            clarification_msg,
            "router_ask_clarification",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="router_ask_clarification",
            outcome="ask_clarification",
            ai_called=False,
            cost_status="none",
        )
        return _PHASE_HALT

    # 6. answer_question (resume_original_question or answer_new_question)
    # When router returns this from awaiting_gender/awaiting_clarification, we MUST use original_question
    _resume_original_question = False
    resume_original = (not ai_primary_mode) and (
        conv_state.get("awaiting_gender") or conv_state.get("awaiting_clarification")
    )
    if resume_original:
        orig = (
            conv_state.get("original_question")
            or user_data.get("original_question")
            or user_data.get("pending_clarification_query")
            or user_data.get("initial_user_query_to_process")
        )
        if orig:
            user_data["awaiting_gender"] = False
            user_data["awaiting_clarification"] = False
            user_data["pending_clarification_query"] = None
            user_data["initial_user_query_to_process"] = None
            if conv_state.get("awaiting_gender"):
                detected_g = get_gender_from_message(user_input_to_process)
                if detected_g in ("male", "female"):
                    config.user_gender[user_id] = detected_g
                    config.user_greeting_stage[user_id] = 2
                    config.gender_attempts[user_id] = 0
                    await user_persistence.save_user_gender(
                        user_id, detected_g, phone=user_data.get("phone_number", user_id), name=user_name
                    )
            user_data["selected_service"] = user_input_to_process  # user's answer often is the service
            # Phase 4: For selector, pass combined context so retrieval fetches right knowledge
            query_to_send_to_gpt = f"Original user question: {orig}\nUser follow-up answer: {user_input_to_process}"
            _resume_original_question = True
            print(
                f"[_process_and_respond] 📋 state_after (resume): awaiting_gender=False, awaiting_clarification=False, selected_service={user_input_to_process[:50]}"
            )
        else:
            query_to_send_to_gpt = user_input_to_process
            _resume_original_question = False
    else:
        # answer_question but not from awaiting_gender/clarification (answer_new_question)
        query_to_send_to_gpt = user_input_to_process
        _resume_original_question = False

    is_initial_message_for_gpt = (config.user_greeting_stage[user_id] == 1) and (current_gender == "unknown")
    initial_user_query_to_process_original = user_data.get("initial_user_query_to_process")

    awaiting_confirmation = user_data.get("awaiting_human_handover_confirmation", False)
    awaiting_booking_offer_confirmation = bool(user_data.get("awaiting_booking_offer_confirmation", False))

    gpt_response_data = {}
    query_pre_set_from_booking_confirmation = False

    if awaiting_booking_offer_confirmation:
        booking_confirmation = _classify_booking_offer_confirmation_reply(user_input_to_process)
        if booking_confirmation == "yes":
            booking_origin_query = (
                user_data.get("booking_offer_origin_query")
                or user_data.get("original_question")
                or user_data.get("pending_clarification_query")
                or "new_booking_request"
            )
            user_data["original_question"] = booking_origin_query
            user_data["awaiting_booking_offer_confirmation"] = False
            user_data["booking_offer_origin_query"] = None
            # Pass to GPT with full context – user already discussed service/branch (e.g. tattoo removal Beirut).
            # Do NOT overwrite with "لأي خدمة بتحب تحجز؟" – GPT will use discussed service + user's date/time.
            query_to_send_to_gpt = f"[User confirmed booking. Previously discussed: {booking_origin_query}. User reply: {user_input_to_process}]"
            query_pre_set_from_booking_confirmation = True
            # Do NOT set gpt_response_data – let GPT proceed with submit_booking_intent (or tools) using context.
        elif booking_confirmation == "no":
            user_data["awaiting_booking_offer_confirmation"] = False
            user_data["booking_offer_origin_query"] = None
            gpt_response_data = {
                "action": "answer_question",
                "bot_reply": _build_booking_decline_reply(current_preferred_lang),
                "detected_language": current_preferred_lang,
                "detected_gender": current_gender if current_gender != "unknown" else None,
                "current_gender_from_config": current_gender,
            }
        else:
            # Treat unresolved short acknowledgments as stale and continue normal flow.
            user_data["awaiting_booking_offer_confirmation"] = False
            user_data["booking_offer_origin_query"] = None

    # AI interprets yes/no for handover confirmation - no bot-side keyword matching
    if not gpt_response_data and awaiting_confirmation:
        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
        conversation_history = await get_conversation_context_for_gpt(
            user_id,
            firestore_conversation_id,
            window_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
            alternate_user_id=canonical_user_id,
        )
        last_ai_response_at = (
            await get_conversation_last_ai_response_at(user_id, current_conversation_id, canonical_user_id)
            if current_conversation_id
            else None
        )
        gpt_response_data = await get_bot_chat_response(
            user_id=user_id,
            user_input=user_input_to_process,
            current_context_messages=conversation_history,
            current_gender=current_gender,
            current_preferred_lang=current_preferred_lang,
            response_language=response_language,
            is_initial_message_after_start=is_initial_message_for_gpt,
            initial_user_query_to_process=initial_user_query_to_process_original,
            last_ai_response_at=last_ai_response_at,
        )
    _pack = [
        "ASK_CLARIFICATION_TEMPLATES",
        "_",
        "_build_booking_decline_reply",
        "_classify_booking_offer_confirmation_reply",
        "_resume_original_question",
        "ai_primary_mode",
        "awaiting_booking_offer_confirmation",
        "awaiting_confirmation",
        "booking_confirmation",
        "booking_origin_query",
        "canonical_user_id",
        "clarification_msg",
        "conv_state",
        "conversation_history",
        "current_conversation_id",
        "current_gender",
        "current_preferred_lang",
        "detected_g",
        "firestore_conversation_id",
        "get_bot_chat_response",
        "get_canonical_user_id_and_phone",
        "get_conversation_context_for_gpt",
        "get_conversation_last_ai_response_at",
        "get_dynamic_message",
        "get_gender_from_message",
        "gpt_response_data",
        "initial_user_query_to_process_original",
        "is_initial_message_for_gpt",
        "last_ai_response_at",
        "log_interaction",
        "orig",
        "query_pre_set_from_booking_confirmation",
        "query_to_send_to_gpt",
        "response_language",
        "resume_original",
        "router_action",
        "router_reply_lang",
        "save_conversation_message_to_firestore",
        "send_message_func",
        "user_data",
        "user_id",
        "user_input_to_process",
        "user_name",
        "user_persistence",
    ]
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
