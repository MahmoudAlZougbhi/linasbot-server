"""Core _process_and_respond phase 8."""

from __future__ import annotations

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase8(ctx: dict):
    action = ctx.get("action")
    bot_reply_text = ctx.get("bot_reply_text")
    current_preferred_lang = ctx.get("current_preferred_lang")
    flow_meta = ctx.get("flow_meta")
    get_dynamic_message = ctx.get("get_dynamic_message")
    _actions_requiring_bot_text = {
        "initial_greet_and_ask_gender",
        "ask_gender",
        "confirm_gender",
        "confirm_booking_details",
        "human_handover_initial_ask",
        "return_to_normal_chat",
        "ask_for_details_for_booking",
        "ask_for_service_type",
        "ask_for_details",
        "ask_for_tattoo_photo",
        "ask_clarification",
        "answer_question",
        "normal_chat",
        "unknown_query",
        "provide_info",
        "tool_call",
        "check_customer_status",
        "confirm_appointment_reschedule",
        "rate_limit_exceeded",
        "content_moderated",
    }
    if action in _actions_requiring_bot_text and not (bot_reply_text or "").strip():
        bot_reply_text = (
            get_dynamic_message("generic_error_message", current_preferred_lang)
            or "عذراً، لم أتمكن من توليد رد الآن. حاول مرة أخرى."
        )
        print(
            f"[_process_and_respond] WARN: Empty bot_reply for action={action} → generic fallback "
            f"(flow_meta.error={flow_meta.get('error')!r})"
        )

    bot_reply_text = str(bot_reply_text or "")

    # Track what we send for flow logging
    sent_reply: str = bot_reply_text
    _pack = [
        "_actions_requiring_bot_text",
        "action",
        "bot_reply_text",
        "current_preferred_lang",
        "flow_meta",
        "get_dynamic_message",
        "sent_reply",
    ]
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
