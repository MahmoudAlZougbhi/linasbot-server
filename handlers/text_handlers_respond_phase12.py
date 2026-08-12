"""Core _process_and_respond phase 12."""
from __future__ import annotations

import datetime
import time

import config
from services.analytics_events import analytics

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase12(ctx: dict):
    _flow_error_reason = ctx.get('_flow_error_reason')
    action = ctx.get('action')
    ai_primary_mode = ctx.get('ai_primary_mode')
    bot_reply_text = ctx.get('bot_reply_text')
    count_tokens = ctx.get('count_tokens')
    current_conversation_id = ctx.get('current_conversation_id')
    current_gender = ctx.get('current_gender')
    current_preferred_lang = ctx.get('current_preferred_lang')
    detected_gender_from_gpt = ctx.get('detected_gender_from_gpt')
    flow_meta = ctx.get('flow_meta')
    flow_source = ctx.get('flow_source')
    flow_steps = ctx.get('flow_steps')
    get_system_instruction = ctx.get('get_system_instruction')
    log_interaction = ctx.get('log_interaction')
    msg_type = ctx.get('msg_type')
    response_time_ms = ctx.get('response_time_ms')
    router_action = ctx.get('router_action')
    save_for_training_conversation_log = ctx.get('save_for_training_conversation_log')
    sent_reply = ctx.get('sent_reply')
    start_time = ctx.get('start_time')
    user_data = ctx.get('user_data')
    user_id = ctx.get('user_id')
    user_input_to_process = ctx.get('user_input_to_process')
    user_name = ctx.get('user_name')
    flow_error_for_log = flow_meta.get("error") or _flow_error_reason
    log_interaction(
        user_id,
        user_input_to_process,
        sent_reply or "",
        flow_source,
        user_name=user_name,
        user_phone=user_data.get("phone_number"),
        user_gender=current_gender,
        customer_exists=user_data.get("crm_customer_exists"),
        customer_file_status=user_data.get("customer_file_status"),
        ai_query_summary=flow_meta.get("ai_query_summary"),
        bot_sent_to_ai_full=flow_meta.get("bot_sent_to_ai"),
        customer_context_sent=flow_meta.get("customer_context_sent"),
        ai_raw_response=flow_meta.get("ai_raw_response"),
        model=flow_meta.get("final_response_model") or flow_meta.get("model"),
        tokens=flow_meta.get("tokens"),
        prompt_tokens=flow_meta.get("prompt_tokens"),
        completion_tokens=flow_meta.get("completion_tokens"),
        cost_usd=flow_meta.get("cost_usd"),
        input_cost_usd=flow_meta.get("input_cost_usd"),
        output_cost_usd=flow_meta.get("output_cost_usd"),
        response_time_ms=response_time_ms,
        tool_calls=flow_meta.get("tool_calls"),
        flow_steps=flow_steps,
        flow_error=flow_error_for_log,
        token_source="backend" if flow_meta.get("prompt_tokens") is not None else None,
        message_type=msg_type,
        user_data=user_data,
        conversation_id=current_conversation_id,
        handler_path="ai_orchestration",
        outcome=action or flow_source,
        ai_called=True,
        cost_status="estimated" if flow_meta.get("cost_usd") is not None else "unavailable",
        cost_basis="openai_usage_tokens_x_configured_rates" if flow_meta.get("cost_usd") is not None else None,
        pipeline_decisions=[
            {"step": "router", "decision": "ai_decides" if ai_primary_mode else (router_action or "ai")},
            {"step": "action", "decision": action or flow_source},
            {
                "step": "handoff",
                "decision": action in ("human_handover", "human_handover_confirmed"),
            },
        ],
    )

    # Token counting and cost: prefer real GPT usage from flow_meta when available
    prompt_tokens = flow_meta.get("prompt_tokens") or 0
    completion_tokens = flow_meta.get("completion_tokens") or 0
    cost = flow_meta.get("cost_usd") or 0.0
    if cost == 0 and user_input_to_process.strip() and not user_input_to_process.lower().startswith("/start"):
        prompt_tokens = count_tokens(
            get_system_instruction(user_id, current_preferred_lang) + "\n\n" + user_input_to_process
        )
        completion_tokens = count_tokens(bot_reply_text)
        fallback_model = flow_meta.get("final_response_model") or flow_meta.get("model") or "gpt-5.1"
        fallback_pricing = {
            "gpt-5.1": (1.25, 10.0),
            "gpt-5.4": (1.25, 10.0),
            "gpt-5.4-mini": (0.25, 2.0),
            "gpt-5-mini": (0.25, 2.0),
        }
        input_per_1m, output_per_1m = fallback_pricing.get(fallback_model, fallback_pricing["gpt-5.1"])
        cost = (prompt_tokens / 1_000_000 * input_per_1m) + (completion_tokens / 1_000_000 * output_per_1m)
        print(
            f"[_process_and_respond] 🔹 Prompt tokens: {prompt_tokens} | Completion: {completion_tokens} | Est. cost: ${cost:.6f}"
        )
        save_for_training_conversation_log(user_input_to_process, bot_reply_text)

    # 📊 ANALYTICS: Log bot's response with performance metrics
    response_time_ms = (time.time() - start_time) * 1000
    analytics.log_message(
        source="bot",
        msg_type="text",
        user_id=user_id,
        language=current_preferred_lang,
        tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
        model=flow_meta.get("final_response_model") or flow_meta.get("model") or "gpt-5.1",
        response_time_ms=response_time_ms,
        message_length=len(bot_reply_text) if bot_reply_text else 0,
    )

    # 📊 ANALYTICS: Log gender if detected
    if detected_gender_from_gpt and detected_gender_from_gpt in ["male", "female"]:
        analytics.log_gender(user_id, detected_gender_from_gpt)

    # 📊 ANALYTICS: Log escalation if human handover
    if action in ["human_handover", "human_handover_confirmed"]:
        analytics.log_escalation(user_id=user_id, escalation_type="human_handover", reason="user_requested")

    # 📊 ANALYTICS: Detect and log service requests
    service_keywords = {
        "laser_hair_removal": ["hair removal", "إزالة الشعر", "ليزر الشعر", "شعر", "hair", "épilation"],
        "tattoo_removal": ["tattoo", "وشم", "tatouage", "remove tattoo", "إزالة وشم"],
        "co2_laser": ["co2", "acne", "حب الشباب", "acné", "skin treatment"],
        "skin_whitening": ["whitening", "تبييض", "blanchiment", "skin lightening"],
        "botox": ["botox", "بوتوكس"],
        "fillers": ["filler", "حشو", "remplissage"],
    }

    # Check user input and bot reply for service mentions
    combined_text = (user_input_to_process + " " + (bot_reply_text or "")).lower()

    for service, keywords in service_keywords.items():
        if any(keyword.lower() in combined_text for keyword in keywords):
            analytics.log_service_request(user_id=user_id, service=service)
            print(f"📊 Analytics: Detected service request - {service}")
            break  # Only log one service per message to avoid duplicates

    config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    return _PHASE_HALT
    _pack = ['_flow_error_reason', 'action', 'ai_primary_mode', 'bot_reply_text', 'combined_text', 'completion_tokens', 'cost', 'count_tokens', 'current_conversation_id', 'current_gender', 'current_preferred_lang', 'detected_gender_from_gpt', 'fallback_model', 'fallback_pricing', 'flow_error_for_log', 'flow_meta', 'flow_source', 'flow_steps', 'get_system_instruction', 'input_per_1m', 'keyword', 'keywords', 'log_interaction', 'msg_type', 'output_per_1m', 'prompt_tokens', 'response_time_ms', 'router_action', 'save_for_training_conversation_log', 'sent_reply', 'service', 'service_keywords', 'start_time', 'user_data', 'user_id', 'user_input_to_process', 'user_name']
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
