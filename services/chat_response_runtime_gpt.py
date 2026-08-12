"""First GPT call and ask_gender short-circuit."""

from __future__ import annotations

from services.chat_response_runtime_common import (
    LEGACY_BOOKING_TOOL_NAMES,
    Any,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ResponseFormatJSONObject,
    _parse_gpt_response_json,
    cast,
    client,
    get_openai_tools_schema,
    json,
)


async def call_first_gpt(ns: Any) -> Any:
    ns.final_response_model_used = ns.selected_model
    ns.response = await client.chat.completions.create(
        model=ns.selected_model,
        messages=cast(list[ChatCompletionMessageParam], ns.messages),
        temperature=0.7,
        tools=cast(
            list[ChatCompletionToolParam],
            get_openai_tools_schema(excluded_tool_names=set(LEGACY_BOOKING_TOOL_NAMES)),
        ),
        tool_choice="auto",
        response_format=cast(ResponseFormatJSONObject, {"type": "json_object"}),
    )

    if not ns.response.choices:
        raise ValueError("GPT returned no choices")
    ns.first_response_message = ns.response.choices[0].message

    ns.gpt_raw_content = ns.first_response_message.content.strip() if ns.first_response_message.content else ""
    print(f"GPT Raw Response (first pass): {ns.gpt_raw_content}")

    ns.tool_calls = ns.first_response_message.tool_calls

    ns.parsed_response: dict[str, Any] = {}
    ns.latest_pricing_payload = None
    ns.api_failure_reason = None  # Set when create_appointment/other API fails → flow_meta.error → human handover (submit_booking_intent uses sanitized tool hints + AI reply, no raw exceptions)
    ns.update_appointment_date_success_count = 0  # Successful date/edit updates this turn (bulk guard)
    ns.pause_resume_success_count = (
        0  # Successful pause-lift actions (date update auto-resume or direct resume_appointment)
    )
    ns.pause_resume_attempted = False
    ns._pause_resume_confirmed_via_date_update = False
    ns.direct_resume_success = False
    ns.paused_followup_update_succeeded = False
    ns.paused_followup_available_action_requested = False
    ns.tool_round_trips: list[dict[str, Any]] = []
    ns.extra_tool_names: list[str] = []
    ns.ai_first_response_with_tools = ""
    ns.recovered_create_appointment_ok = False
    ns.booking_create_attempted_this_turn = False

    # When GPT asks for gender (unknown), send that reply and do NOT run tool calls.
    # Otherwise a second response after tools can replace it with booking flow (date/time/branch).
    if ns.tool_calls and ns.current_gender == "unknown" and ns.gpt_raw_content:
        try:
            ns.first_parsed = _parse_gpt_response_json(ns.gpt_raw_content)
            ns.first_action = (ns.first_parsed.get("action") or "").strip().lower()
            if ns.first_action in ["ask_gender", "initial_greet_and_ask_gender"]:
                ns.first_parsed.setdefault("detected_language", ns.current_preferred_lang)
                ns.first_parsed["current_gender_from_config"] = ns.current_gender
                ns.first_parsed.setdefault("detected_gender", None)
                ns.first_parsed.setdefault("detected_name", None)
                ns.first_parsed["_flow_meta"] = {
                    "model": ns.selected_model,
                    "ai_raw_response": ns.gpt_raw_content[:2000] if ns.gpt_raw_content else None,
                    "ai_query_summary": ns.flow_ai_query_summary,
                    "bot_sent_to_ai": ns.flow_bot_sent_to_ai_full,
                    "customer_context_sent": ns.flow_customer_context_sent,
                }
                print(
                    "PRIORITY: First response is ask_gender (gender unknown). Skipping tool calls and sending gender question."
                )
                return ns.first_parsed
        except (json.JSONDecodeError, TypeError):
            pass
