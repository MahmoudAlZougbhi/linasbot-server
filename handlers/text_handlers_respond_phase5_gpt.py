"""GPT continuation for _process_and_respond phase 5 (no FAQ match)."""

from __future__ import annotations

from typing import Any, cast

import config
from services.analytics_events import analytics


async def text_handlers_respond_phase5_gpt(pctx: dict) -> Any:
    _apply_turn_by_turn_policy = cast(Any, pctx.get("_apply_turn_by_turn_policy"))
    _build_arabic_respectful_address = cast(Any, pctx.get("_build_arabic_respectful_address"))
    _is_price_intent = cast(Any, pctx.get("_is_price_intent"))
    _resume_original_question = cast(Any, pctx.get("_resume_original_question"))
    ai_primary_mode = cast(Any, pctx.get("ai_primary_mode"))
    canonical_user_id = cast(Any, pctx.get("canonical_user_id"))
    conv_state = cast(Any, pctx.get("conv_state"))
    conversation_history = cast(Any, pctx.get("conversation_history"))
    current_conversation_id = cast(Any, pctx.get("current_conversation_id"))
    current_gender = cast(Any, pctx.get("current_gender"))
    current_preferred_lang = cast(Any, pctx.get("current_preferred_lang"))
    detect_reschedule_intent = cast(Any, pctx.get("detect_reschedule_intent"))
    firestore_conversation_id = cast(Any, pctx.get("firestore_conversation_id"))
    get_bot_chat_response = cast(Any, pctx.get("get_bot_chat_response"))
    get_canonical_user_id_and_phone = cast(Any, pctx.get("get_canonical_user_id_and_phone"))
    get_conversation_context_for_gpt = cast(Any, pctx.get("get_conversation_context_for_gpt"))
    get_conversation_last_ai_response_at = cast(Any, pctx.get("get_conversation_last_ai_response_at"))
    get_dynamic_message = cast(Any, pctx.get("get_dynamic_message"))
    get_last_bot_message_for_gpt_context = cast(Any, pctx.get("get_last_bot_message_for_gpt_context"))
    gpt_response_data = cast(Any, pctx.get("gpt_response_data"))
    initial_user_query_to_process_original = cast(Any, pctx.get("initial_user_query_to_process_original"))
    is_initial_message_for_gpt = cast(Any, pctx.get("is_initial_message_for_gpt"))
    is_post_takeover_escalation_cooldown = cast(Any, pctx.get("is_post_takeover_escalation_cooldown"))
    last_ai_response_at = cast(Any, pctx.get("last_ai_response_at"))
    local_qa_service = cast(Any, pctx.get("local_qa_service"))
    log_interaction = cast(Any, pctx.get("log_interaction"))
    query_to_send_to_gpt = cast(Any, pctx.get("query_to_send_to_gpt"))
    respectful_address = cast(Any, pctx.get("respectful_address"))
    response_language = cast(Any, pctx.get("response_language"))
    save_conversation_message_to_firestore = cast(Any, pctx.get("save_conversation_message_to_firestore"))
    save_for_training_conversation_log = cast(Any, pctx.get("save_for_training_conversation_log"))
    send_message_func = cast(Any, pctx.get("send_message_func"))
    update_dashboard_metric_in_firestore = cast(Any, pctx.get("update_dashboard_metric_in_firestore"))
    user_data = cast(Any, pctx.get("user_data"))
    user_id = cast(Any, pctx.get("user_id"))
    user_image_base64 = cast(Any, pctx.get("user_image_base64"))
    user_image_format = cast(Any, pctx.get("user_image_format"))
    user_input_to_process = cast(Any, pctx.get("user_input_to_process"))
    user_name = cast(Any, pctx.get("user_name"))
    is_reschedule_intent = cast(Any, pctx.get("is_reschedule_intent"))
    is_price_intent = cast(Any, pctx.get("is_price_intent"))
    if ai_primary_mode:
        print("[_process_and_respond] 🧠 AI-primary mode ON. No FAQ match >=90%, continuing AI-normal flow.")
    if is_reschedule_intent:
        print("[_process_and_respond] 🔁 Reschedule intent detected. No FAQ match >=90%, continuing booking flow.")
    if is_price_intent:
        print("[_process_and_respond] 💰 Price intent detected. No FAQ match >=90%, continuing exact pricing flow.")
    # <90% match: GPT + knowledge + style + top 3 relevant Q&A pairs
    print("[_process_and_respond] ℹ️ No Q&A match found (below 90%). Proceeding with GPT-4...")
    print("[_process_and_respond] 💡 GPT will receive top 3 relevant Q&A pairs in context")

    # Fetch conversation history once (same 12h window as normal context) – use for selector and for GPT.
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
    last_bot_msg = await get_last_bot_message_for_gpt_context(
        user_id,
        current_conversation_id,
        canonical_user_id,
        within_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
    )

    if last_bot_msg and query_to_send_to_gpt:
        try:
            _meta = last_bot_msg.get("metadata") or {}
            if _meta.get("source") == "smart_message" and _meta.get("type") == "reminder_24h":
                from utils.reminder_analytics import classify_reminder_reply_intent

                _rint = classify_reminder_reply_intent(query_to_send_to_gpt)
                if _rint:
                    _pn = user_data.get("phone_number")
                    analytics.log_smart_reminder_reply(
                        user_id=user_id,
                        intent=_rint,
                        source_message_id=_meta.get("message_id"),
                        appointment_id=_meta.get("appointment_id"),
                        phone=str(_pn).strip() if _pn else None,
                    )
        except Exception as _ra:
            print(f"[_process_and_respond] reminder reply analytics: {_ra}")

    # ALWAYS run selector: pass query + context_messages so selector understands what the conversation is about (e.g. user "eh" / "beirut" after we asked branch).
    from services.dynamic_retrieval_service import (
        is_dynamic_retrieval_available,
        retrieve_and_merge,
    )

    custom_context = None
    _dynamic_retrieval_flow_meta = None
    selector_query = query_to_send_to_gpt
    if user_image_base64:
        selector_query = (
            "The user sent an image (attached below). Examine the image and the conversation context. "
            "Select which files to load. Do not assume – pick based on what you observe."
        )
    if is_dynamic_retrieval_available():
        merged, _clar, _act, _dynamic_retrieval_flow_meta = await retrieve_and_merge(
            selector_query,
            include_price_hint=is_price_intent,
            response_lang=current_preferred_lang,
            context_messages=conversation_history,
            user_image_base64=user_image_base64,
            user_image_format=user_image_format,
        )
        custom_context = merged if merged else None
        print(f"[_process_and_respond] ✅ Selector ran: action={_act}, context_len={len(custom_context or '')}")
        if custom_context:
            from services.ai_limits_enforcement import enforce_context_line_budget

            custom_context, ctx_decision = enforce_context_line_budget(
                user_id=user_id,
                user_data=user_data,
                text=custom_context,
                consume=True,
            )
            if not custom_context and not ctx_decision.allowed:
                custom_context = None
                print(
                    f"[_process_and_respond] context_lines_blocked reason={ctx_decision.reason}",
                    flush=True,
                )

    # Phase 3: Build operational context when resuming (Plan §10)
    operational_context = None
    if user_data.pop("just_returned_from_human_takeover", False):
        takeover_ctx = (
            "**USER JUST RETURNED FROM HUMAN TAKEOVER (CRITICAL):**\n"
            "- A human operator just finished with this user. The conversation was released back to the bot.\n"
            "- **Conversation history sent to you may omit messages from before the release** (technical reset for a clean AI session).\n"
            "- Do NOT re-escalate to human based on OLD frustration or complaints that are no longer in the history.\n"
            "- Only hand over if the user EXPLICITLY asks for a human in THIS current message.\n"
            "- Treat this as a fresh start. Answer their current question normally."
        )
        operational_context = (operational_context + "\n\n" + takeover_ctx) if operational_context else takeover_ctx
    if _resume_original_question:
        orig_q = user_data.get("original_question") or conv_state.get("original_question")
        ctx = (
            f"Conversation State:\n"
            f"- gender: {current_gender}\n"
            f"- awaiting_gender: false\n"
            f"- awaiting_clarification: false\n"
            f'- original_question: "{orig_q or ""}"\n'
            f'- selected_service: "{user_data.get("selected_service", "")}"\n'
            f'- last_bot_question_type: "{conv_state.get("last_bot_question_type", "")}"\n\n'
            f'Current User Message: "{user_input_to_process}"\n\n'
            f"Task: The user previously asked a question. The bot asked for clarification or gender. "
            f"The user has now answered. Answer the ORIGINAL question. Do not ask for clarification again."
        )
        operational_context = (operational_context + "\n\n" + ctx) if operational_context else ctx
    # When last message was from us (e.g. smart message, notification): give GPT context so it doesn't lose domain
    if last_bot_msg and last_bot_msg.get("text"):
        last_text = (last_bot_msg.get("text") or "")[:500]
        is_smart = (last_bot_msg.get("metadata") or {}).get("source") == "smart_message"
        ctx = f'Last message we sent to the user: "{last_text}"\nDomain: clinic (ليناز ليزر). '
        if is_smart:
            ctx += "This was a clinic notification. The user might be replying to or asking about it. "
        ctx += "Do not lose context – the user might be talking or asking about this."
        operational_context = (operational_context + "\n\n" + ctx) if operational_context else ctx

    if is_post_takeover_escalation_cooldown(user_data):
        cooldown_ctx = (
            "**POST-RELEASE COOLDOWN (CRITICAL):** This user was recently returned to the bot from human support.\n"
            "- Do NOT set handover_degree to medium or high based on old messages or past frustration.\n"
            "- Do NOT choose action human_handover unless they clearly ask to speak to a person **in this message**.\n"
            "- Answer their current message normally; ignore stale anger/complaints in history for escalation."
        )
        operational_context = (operational_context + "\n\n" + cooldown_ctx) if operational_context else cooldown_ctx

    gpt_response_data = await get_bot_chat_response(
        user_id=user_id,
        user_input=query_to_send_to_gpt,
        current_context_messages=conversation_history,
        current_gender=current_gender,
        current_preferred_lang=current_preferred_lang,
        response_language=response_language,
        is_initial_message_after_start=is_initial_message_for_gpt,
        initial_user_query_to_process=None,
        custom_knowledge_context=custom_context,
        operational_context=operational_context,
        last_ai_response_at=last_ai_response_at,
        user_image_base64=user_image_base64,
        user_image_format=user_image_format,
    )
    _pack = [
        "_",
        "_act",
        "_clar",
        "_dynamic_retrieval_flow_meta",
        "_meta",
        "_pn",
        "_rint",
        "canonical_user_id",
        "classify_reminder_reply_intent",
        "conversation_history",
        "cooldown_ctx",
        "ctx",
        "ctx_decision",
        "custom_context",
        "enforce_context_line_budget",
        "gpt_response_data",
        "is_dynamic_retrieval_available",
        "is_price_intent",
        "is_reschedule_intent",
        "is_smart",
        "last_ai_response_at",
        "last_bot_msg",
        "last_text",
        "merged",
        "operational_context",
        "orig_q",
        "query_to_send_to_gpt",
        "retrieve_and_merge",
        "selector_query",
        "takeover_ctx",
    ]
    for _k in _pack:
        if _k in locals():
            pctx[_k] = locals()[_k]
    return None
