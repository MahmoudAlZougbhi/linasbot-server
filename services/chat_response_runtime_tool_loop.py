"""Tool-call loop for get_bot_chat_response."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    BOOKING_TZ,
    FINAL_RESPONSE_MODEL,
    LOOP_CONTINUE,
    Any,
    ChatCompletionMessageParam,
    ResponseFormatJSONObject,
    _build_pause_resume_execution_guardrail,
    _merge_pricing_args_with_booking_state,
    _normalize_profile_gender,
    _parse_gpt_response_json,
    _record_tool_round_trip,
    _remember_booking_selection,
    _safe_int,
    _update_current_conversation_customer_info,
    _update_profile_name_in_firestore,
    _validate_profile_name,
    cast,
    client,
    config,
    extract_appointment_booking_fields,
    find_appointment_row_in_check_next_payload,
    json,
    parse_normalized_api_datetime,
    validate_booking_slot,
)
from services.chat_response_runtime_tool_create_name import handle_create_appointment_name
from services.chat_response_runtime_tool_create_payload import handle_create_appointment_payload
from services.chat_response_runtime_tool_execute import handle_execute_api_tool
from services.chat_response_runtime_tool_helpers import bind_tool_helpers
from services.chat_response_runtime_tool_submit import handle_retrieve_or_submit_tools
from services.chat_response_runtime_tool_update import handle_update_appointment_tools


async def run_tool_loop(ns: Any) -> Any:
    if not ns.tool_calls:
        ns.parsed_response = _parse_gpt_response_json(ns.gpt_raw_content)
        return None
    ns.messages.append(ns.first_response_message.model_dump(exclude_none=True))
    ns.tool_round_trips.clear()
    ns.ai_first_response_with_tools = ns.gpt_raw_content  # Save before overwrite

    # Track check_next_appointment result to auto-chain appointment_id for update_appointment_date
    ns.check_next_appointment_result = None
    ns.paused_appointment_lookup_cache: dict[str, Any] = {}
    bind_tool_helpers(ns)
    for ns.tool_call in ns.tool_calls:
        ns.fn = getattr(ns.tool_call, "function", None)
        if ns.fn is None:
            continue
        ns.function_name = ns.fn.name
        ns.function_args = json.loads(ns.fn.arguments) if ns.fn.arguments else {}
        ns.all_user_text_for_date = ns.collect_user_datetime_text(ns.current_context_messages, ns.user_input)
        ns.user_requested_change = ns.detect_change_request_intent(ns.all_user_text_for_date) or ns.is_reschedule_intent
        ns.forced_update_appointment_id = None
        ns.booking_state = config.user_booking_state[ns.user_id]

        if ns.function_name == "pause_appointment":
            print("SAFETY: Blocking pause_appointment tool call; AI pause is disabled.")
            ns.err_content = json.dumps(
                {
                    "success": False,
                    "message": "pause_appointment_disabled_for_ai",
                    "hint_for_model": (
                        "pause_appointment is disabled — do not try to pause from chat. "
                        "For a **Paused** row that should become **Available** again at the **same** slot, call **resume_appointment** "
                        "(appointment_id + phone). For a **new** date/time on a paused row, use **update_appointment_date**. "
                        "For edits (areas/machine) on a paused row while making it Available, use **update_paused_appointment** "
                        "and/or **resume_appointment** per tool rules."
                    ),
                },
                ensure_ascii=False,
            )
            ns.tool_round_trips.append(_record_tool_round_trip(ns.function_name, ns.function_args, ns.err_content, None))
            ns.messages.append(
                {
                    "tool_call_id": ns.tool_call.id,
                    "role": "tool",
                    "name": ns.function_name,
                    "content": ns.err_content,
                }
            )
            continue

        if ns.function_name == "update_customer_profile":
            ns.new_name, ns.name_error = _validate_profile_name(
                ns.function_args.get("new_name") or ns.function_args.get("name")
            )
            ns.new_gender = _normalize_profile_gender(
                ns.function_args.get("new_gender") or ns.function_args.get("gender")
            )
            ns.errors = []
            ns.updated_fields: dict[str, Any] = {}

            if ns.name_error:
                ns.errors.append(ns.name_error)
            if (ns.function_args.get("new_gender") or ns.function_args.get("gender")) and not ns.new_gender:
                ns.errors.append("gender_invalid")

            if ns.new_name:
                config.user_names[ns.user_id] = ns.new_name
                if ns.user_id in config.user_data_whatsapp:
                    config.user_data_whatsapp[ns.user_id]["collected_name"] = ns.new_name
                    config.user_data_whatsapp[ns.user_id]["name_source"] = "user_requested_profile_update"
                    config.user_data_whatsapp[ns.user_id]["awaiting_name_input"] = False
                config.user_greeting_stage[ns.user_id] = 2
                ns.name_paths = await _update_profile_name_in_firestore(
                    ns.user_id,
                    ns.new_name,
                    ns.customer_phone_full,
                )
                ns.updated_fields["name"] = {
                    "value": ns.new_name,
                    "firestore_paths_updated": ns.name_paths,
                }
                ns.user_name = ns.new_name

            if ns.new_gender:
                from services.user_persistence_service import user_persistence

                await user_persistence.save_user_gender(
                    ns.user_id,
                    ns.new_gender,
                    phone=ns.customer_phone_full or ns.user_id,
                    name=config.user_names.get(ns.user_id, ns.user_name),
                )
                ns.current_gender = ns.new_gender
                ns.updated_fields["gender"] = {"value": ns.new_gender}

            if ns.updated_fields:
                ns.conv_updates = await _update_current_conversation_customer_info(
                    ns.user_id,
                    config.user_data_whatsapp.get(ns.user_id, {}).get("current_conversation_id"),
                    name=ns.new_name,
                    gender=ns.new_gender,
                    phone_number=ns.customer_phone_full,
                )
                ns.tool_output = {
                    "success": True,
                    "updated_fields": ns.updated_fields,
                    "conversation_customer_info_paths_updated": ns.conv_updates,
                    "message": "profile_updated",
                    "hint_for_model": (
                        "Tell the user briefly that the saved profile was updated. "
                        "Use the corrected name/gender from now on."
                    ),
                }
            else:
                ns.tool_output = {
                    "success": False,
                    "error_type": "missing_or_invalid_profile_update",
                    "errors": ns.errors or ["no_profile_fields_provided"],
                    "hint_for_model": (
                        "Ask the user for the exact new name or whether the gender should be male/female."
                    ),
                }

            ns.tool_content = json.dumps(ns.tool_output, ensure_ascii=False, default=str)
            ns.tool_round_trips.append(
                _record_tool_round_trip(
                    ns.function_name,
                    ns.function_args,
                    ns.tool_content,
                    ns.tool_output,
                )
            )
            ns.messages.append(
                {
                    "tool_call_id": ns.tool_call.id,
                    "role": "tool",
                    "name": ns.function_name,
                    "content": ns.tool_content,
                }
            )
            continue

        # Keep pricing args and persisted booking state in sync.
        _merge_pricing_args_with_booking_state(
            function_name=ns.function_name,
            function_args=ns.function_args,
            booking_state=ns.booking_state,
            current_gender=ns.current_gender,
            user_input=ns.user_input,
        )

        # SAFETY GUARD: Reschedule intent must never route to working-hours tool.
        if ns.function_name == "get_clinic_hours" and (ns.is_reschedule_intent or ns.user_requested_change):
            ns.phone_for_reschedule = (
                ns.function_args.get("phone")
                or ns.customer_phone_clean
                or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
                or ns.user_id
            )
            print(
                f"SAFETY: Re-routing get_clinic_hours -> check_next_appointment for reschedule intent (phone={ns.phone_for_reschedule})."
            )
            ns.function_name = "check_next_appointment"
            ns.function_args = {"phone": ns.phone_for_reschedule}

        # SAFETY GUARD: If the canonical *next* appointment is paused/postponed and the user
        # asks to change/reschedule, never allow create_appointment — force update on that row.
        # Do NOT use an older paused record when the API's "next" slot is an active booking (e.g. Available).
        if ns.function_name == "create_appointment" and ns.user_requested_change:
            ns.phone_for_pause_guard = ns.normalize_phone_for_lookup(
                ns.function_args.get("phone")
                or ns.customer_phone_clean
                or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
                or ns.user_id
            )

            ns.paused_appointment_id = await ns.find_paused_appointment_id(ns.phone_for_pause_guard)
            ns._next_pl_create = (
                ns.extract_check_next_appointment(ns.check_next_appointment_result)
                if ns.check_next_appointment_result
                else {}
            )
            ns._next_id_create = ns.extract_appointment_id(ns._next_pl_create)
            ns._next_st_create = ns.extract_appointment_status(ns._next_pl_create)
            if (
                ns.paused_appointment_id
                and ns._next_id_create is not None
                and ns._next_id_create == ns.paused_appointment_id
                and ns.is_paused_status(ns._next_st_create)
            ):
                ns.requested_date = ns.function_args.get("date")
                ns.function_name = "update_appointment_date"
                ns.function_args = {
                    "appointment_id": ns.paused_appointment_id,
                    "phone": ns.phone_for_pause_guard,
                    "date": ns.requested_date,
                }
                ns.forced_update_appointment_id = ns.paused_appointment_id
                print(
                    f"SAFETY: Converted create_appointment -> update_appointment_date for paused NEXT appointment_id={ns.paused_appointment_id}"
                )

        # --- create_appointment: structured tool args only (no user-text booking inference) ---
        result = await handle_create_appointment_name(ns)
        if result is LOOP_CONTINUE:
            continue
        if result is not None:
            return result
        result = await handle_create_appointment_payload(ns)
        if result is LOOP_CONTINUE:
            continue
        if result is not None:
            return result
        result = await handle_update_appointment_tools(ns)
        if result is LOOP_CONTINUE:
            continue
        if result is not None:
            return result
        # --- Auto-chain appointment_id from check_next when GPT omitted it ---
        # If GPT already set appointment_id (e.g. user picked from a multi-appointment list), do not overwrite.
        if (
            ns.function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment")
            and ns.check_next_appointment_result
            and not ns.forced_update_appointment_id
        ):
            ns.actual_appointment_id = ns.extract_appointment_id(
                ns.extract_check_next_appointment(ns.check_next_appointment_result)
            )
            if ns.actual_appointment_id:
                ns.gpt_raw = ns.function_args.get("appointment_id")
                try:
                    ns.gpt_provided_id = int(ns.gpt_raw) if ns.gpt_raw is not None and ns.gpt_raw != "" else None
                except (TypeError, ValueError):
                    ns.gpt_provided_id = None
                if ns.gpt_provided_id is None:
                    print(f"DEBUG: Auto-chaining appointment_id (missing) -> {ns.actual_appointment_id}")
                    ns.function_args["appointment_id"] = ns.actual_appointment_id
                elif ns.gpt_provided_id != ns.actual_appointment_id:
                    print(
                        f"DEBUG: Keeping GPT appointment_id={ns.gpt_provided_id} (check_next next id={ns.actual_appointment_id})"
                    )
                else:
                    print(f"DEBUG: appointment_id already correct: {ns.actual_appointment_id}")

        # Reject day/time that violate clinic rules (service + gender + branch + device) before CRM.
        if ns.function_name in (
            "create_appointment",
            "update_appointment_date",
            "update_paused_appointment",
            "edit_appointment",
        ):
            ns.date_s = ns.function_args.get("date")
            ns.dt_local = None
            if isinstance(ns.date_s, str) and ns.date_s.strip():
                ns.dt_local = parse_normalized_api_datetime(ns.date_s.strip(), BOOKING_TZ)
            if ns.dt_local is not None:
                ns.sid = ns.bid = None
                ns.mid: int | None = None
                if ns.function_name == "create_appointment":
                    ns.sid = _safe_int(ns.function_args.get("service_id"))
                    ns.bid = _safe_int(ns.function_args.get("branch_id"))
                    ns.mid = _safe_int(ns.function_args.get("machine_id"))
                elif ns.function_name == "edit_appointment":
                    ns.aid = _safe_int(ns.function_args.get("appointment_id"))
                    ns.row = find_appointment_row_in_check_next_payload(ns.check_next_appointment_result, ns.aid)
                    if ns.row is not None:
                        ns.sid, ns.bid, ns.mid = extract_appointment_booking_fields(ns.row)
                    else:
                        ns.sid = _safe_int(ns.function_args.get("service_id"))
                        ns.bid = _safe_int(ns.function_args.get("branch_id"))
                        ns.mid = _safe_int(ns.function_args.get("machine_id"))
                else:
                    ns.aid = _safe_int(ns.function_args.get("appointment_id"))
                    ns.row = find_appointment_row_in_check_next_payload(ns.check_next_appointment_result, ns.aid)
                    if ns.row is not None:
                        ns.sid, ns.bid, ns.mid = extract_appointment_booking_fields(ns.row)
                    else:
                        print(
                            "DEBUG: slot_validation skipped update_appointment_date "
                            f"(no CRM row for appointment_id={ns.aid})"
                        )
                if ns.sid is not None and ns.bid is not None:
                    ns.vr = validate_booking_slot(
                        dt_local=ns.dt_local,
                        service_id=ns.sid,
                        branch_id=ns.bid,
                        machine_id=ns.mid,
                        gender_raw=ns.current_gender,
                    )
                    if not ns.vr.get("ok"):
                        ns.sv = ns.vr.get("slot_validation") or {}
                        ns.err_content = json.dumps(
                            {
                                "success": False,
                                "message": ns.sv.get(
                                    "explanation_en",
                                    "This day/time is not available for the selected service, branch, and gender.",
                                ),
                                "slot_validation": ns.sv,
                            }
                        )
                        ns.tool_round_trips.append(
                            _record_tool_round_trip(ns.function_name, ns.function_args, ns.err_content, None)
                        )
                        ns.messages.append(
                            {
                                "tool_call_id": ns.tool_call.id,
                                "role": "tool",
                                "name": ns.function_name,
                                "content": ns.err_content,
                            }
                        )
                        continue

        _remember_booking_selection(ns.user_id, ns.function_args)
        result = await handle_retrieve_or_submit_tools(ns)
        if result is LOOP_CONTINUE:
            continue
        if result is not None:
            return result
        result = await handle_execute_api_tool(ns)
        if result is LOOP_CONTINUE:
            continue
        if result is not None:
            return result
    ns.messages.append(
        {
            "role": "system",
            "content": _build_pause_resume_execution_guardrail(
                resume_attempted=ns.pause_resume_attempted,
                resume_succeeded=(ns.pause_resume_success_count > 0),
                date_update_succeeded=(ns.update_appointment_date_success_count > 0),
                direct_resume_succeeded=ns.direct_resume_success,
            ),
        }
    )
    ns.second_response = await client.chat.completions.create(
        model=FINAL_RESPONSE_MODEL,
        messages=cast(list[ChatCompletionMessageParam], ns.messages),
        response_format=cast(ResponseFormatJSONObject, {"type": "json_object"}),
    )
    ns.final_response_model_used = FINAL_RESPONSE_MODEL
    if not ns.second_response.choices:
        raise ValueError("GPT returned no choices (after tool call)")
    ns.gpt_raw_content = (
        ns.second_response.choices[0].message.content.strip() if ns.second_response.choices[0].message.content else ""
    )
    print(f"GPT Raw Response (after tool call): {ns.gpt_raw_content}")

    ns.parsed_response = _parse_gpt_response_json(ns.gpt_raw_content)
    return None

