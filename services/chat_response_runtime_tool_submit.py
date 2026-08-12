"""retrieve_relevant_knowledge and submit_booking_intent tools."""

from __future__ import annotations

from services.chat_response_runtime_common import (
    _SUBMIT_BOOKING_TOOL_HINT_TECHNICAL,
    Any,
    _booking_submit_payload_complete_for_execution,
    _extract_direct_submit_booking_args_from_user_message,
    _merge_explicit_user_booking_args,
    _record_tool_round_trip,
    _sanitize_submit_booking_tool_for_model,
    asyncio,
    config,
    detect_bulk_reschedule_all_intent,
    json,
)


async def handle_retrieve_or_submit_tools(ns: Any) -> Any:
    if ns.function_name == "retrieve_relevant_knowledge":
        ns.user_msg = ns.function_args.get("user_message", ns.user_input)
        try:
            from services.dynamic_retrieval_service import (
                _ensure_style_included,
                _get_default_general_and_style,
                _load_content_by_ids,
                is_dynamic_retrieval_available,
                select_files_llm,
            )

            if is_dynamic_retrieval_available():
                ns.result = await select_files_llm(ns.user_msg)
                ns.action = ns.result.get("action", "fallback_to_general")
                ns.files = ns.result.get("files", [])
                if ns.action == "ask_clarification":
                    ns.tool_output = {
                        "action": "ask_clarification",
                        "content": "",
                        "message": "User message needs clarification. Ask the user which service they mean (hair removal, tattoo, whitening, etc.).",
                    }
                elif ns.files:
                    ns.merged, ns.has_style = _load_content_by_ids(ns.files)
                    ns.merged = (
                        _ensure_style_included(ns.merged, ns.has_style)
                        if ns.merged
                        else _get_default_general_and_style()
                    )
                    ns.tool_output = {"action": "normal", "content": ns.merged or "", "files_loaded": ns.files}
                else:
                    ns.merged = _get_default_general_and_style()
                    ns.merged = _ensure_style_included(ns.merged, False)
                    ns.tool_output = {"action": "fallback_to_general", "content": ns.merged or ""}
            else:
                # ===== CM AI CONTROL PLANE — published-mode runtime (plan §12) =====
                from services.cm.constants import cm_runtime_mode as _cm_mode

                ns.kb = "" if _cm_mode() == "published" else (config.CORE_KNOWLEDGE_BASE or "")
                ns.tool_output = {"action": "fallback_to_general", "content": ns.kb}
            ns.tool_content = json.dumps(ns.tool_output, default=str)
            ns.tool_round_trips.append(
                _record_tool_round_trip(ns.function_name, ns.function_args, ns.tool_content, None)
            )
            ns.messages.append(
                {
                    "tool_call_id": ns.tool_call.id,
                    "role": "tool",
                    "name": ns.function_name,
                    "content": ns.tool_content,
                }
            )
        except Exception as kr_e:
            print(f"⚠️ retrieve_relevant_knowledge error: {kr_e}")
            ns.err_content = json.dumps({"success": False, "content": "", "message": str(kr_e)})
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
    elif ns.function_name == "submit_booking_intent":
        from services.booking.booking_fsm import (
            can_execute_submit,
            human_gate_message,
            mark_booking_completed,
            parse_gate_reason,
        )
        from services.booking.booking_fsm import (
            fsm_enabled as _fsm_gate_enabled,
        )
        from services.booking.booking_fsm import (
            merge_patch as _fsm_merge_patch,
        )
        from services.booking.intent_pipeline import handle_submit_booking_intent
        from services.booking.schemas import validation_error_response
        from services.product_features import boc_disabled_response, legacy_booking_tools_disabled

        if legacy_booking_tools_disabled():
            ns.tool_output = boc_disabled_response(operation="tool:submit_booking_intent")
            ns.tool_content = json.dumps(ns.tool_output, default=str)
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
            return

        ns.explicit_submit_args = _extract_direct_submit_booking_args_from_user_message(
            ns.user_input,
            phone=ns.customer_phone_clean
            or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
            or ns.user_id,
            current_gender=ns.current_gender,
            fallback_name=config.user_names.get(ns.user_id, ns.user_name),
        )
        if _merge_explicit_user_booking_args(ns.function_args, ns.explicit_submit_args):
            print(
                "[BOOKING_DIRECT] overlaid explicit user booking args onto submit_booking_intent "
                f"user={ns.user_id} service_id={ns.function_args.get('service_id')} "
                f"date={ns.function_args.get('date')}"
            )

        ns._sb_phone = (
            ns.function_args.get("phone")
            or ns.customer_phone_clean
            or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
            or ""
        )
        if ns.booking_create_attempted_this_turn and not detect_bulk_reschedule_all_intent(ns.user_input):
            ns.tool_output = validation_error_response(
                missing_fields=[],
                human_readable_reason=(
                    "Only one new booking may be executed per user turn unless the user explicitly asks for multiple bookings. "
                    "Ask which second appointment they want to book next."
                ),
                activity_trace={
                    "failure_stage": "multiple_booking_create_blocked",
                    "execution_phase": "pre_execution",
                    "detail": "second submit_booking_intent blocked in same turn",
                    "pipeline_phase": "submit_booking_intent_blocked",
                },
            )
        else:
            ns.booking_create_attempted_this_turn = True
            ns._ok_submit, ns._gate_reason = can_execute_submit(ns.user_id, ns.current_gender)
            if (
                _fsm_gate_enabled()
                and not ns._ok_submit
                and ns._gate_reason == "fsm_confirmation_required"
                and _booking_submit_payload_complete_for_execution(ns.function_args, ns.current_gender)
            ):
                try:
                    _fsm_merge_patch(ns.user_id, {"confirmed_booking": True})
                    ns._ok_submit, ns._gate_reason = can_execute_submit(ns.user_id, ns.current_gender)
                    print(
                        "[BOOKING_FSM] auto-confirmed complete one-message booking payload "
                        f"user={ns.user_id} service_id={ns.function_args.get('service_id')} "
                        f"date={ns.function_args.get('date') or ns.function_args.get('date_components')}"
                    )
                except Exception as _auto_confirm_e:
                    print(f"⚠️ booking_fsm auto-confirm failed: {_auto_confirm_e}")
            if _fsm_gate_enabled() and not ns._ok_submit:
                ns._mf = parse_gate_reason(ns._gate_reason or "")
                ns.tool_output = validation_error_response(
                    missing_fields=ns._mf,
                    human_readable_reason=human_gate_message(ns._gate_reason or "", ns.current_preferred_lang),
                    activity_trace={
                        "failure_stage": "booking_fsm_gate",
                        "execution_phase": "pre_execution",
                        "detail": ns._gate_reason,
                        "pipeline_phase": "submit_booking_intent_blocked",
                    },
                )
            else:
                try:
                    ns.tool_output = await handle_submit_booking_intent(
                        user_id=ns.user_id,
                        phone=str(ns._sb_phone).strip(),
                        current_gender=ns.current_gender,
                        user_input=ns.user_input,
                        function_args=ns.function_args,
                    )
                except Exception as _sb_exc:
                    print(f"ERROR: submit_booking_intent raised: {_sb_exc}")
                    ns.tool_output = {
                        "success": False,
                        "error_type": "submit_exception",
                        "human_readable_reason": _SUBMIT_BOOKING_TOOL_HINT_TECHNICAL,
                        "activity_trace": {
                            "failure_stage": "submit_exception",
                            "detail": f"{type(_sb_exc).__name__}: {str(_sb_exc)[:500]}",
                            "pipeline_phase": "submit_booking_intent",
                        },
                    }
            if (
                isinstance(ns.tool_output, dict)
                and ns.tool_output.get("success")
                and ns.tool_output.get("booking_flow_state") == "booked"
            ):
                try:
                    mark_booking_completed(ns.user_id)
                except Exception as _fsm_mc_e:
                    print(f"⚠️ booking_fsm mark_booking_completed: {_fsm_mc_e}")
        ns._tool_for_model = (
            _sanitize_submit_booking_tool_for_model(ns.tool_output)
            if isinstance(ns.tool_output, dict)
            else ns.tool_output
        )
        ns.tool_content = json.dumps(ns._tool_for_model, default=str)
        ns.tool_round_trips.append(
            _record_tool_round_trip(
                ns.function_name,
                ns.function_args,
                ns.tool_content,
                ns.tool_output if isinstance(ns.tool_output, dict) else None,
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
        if (
            isinstance(ns.tool_output, dict)
            and ns.tool_output.get("success")
            and ns.tool_output.get("booking_flow_state") == "booked"
        ):
            ns.recovered_create_appointment_ok = True
            try:
                from services.analytics_events import analytics

                ns.api_wrapped_raw = ns.tool_output.get("api_response")
                ns.api_wrapped = ns.api_wrapped_raw if isinstance(ns.api_wrapped_raw, dict) else {}
                ns.raw_data_payload = ns.api_wrapped.get("data", {})
                ns.appointment_data_raw = (
                    ns.raw_data_payload.get("appointment") if isinstance(ns.raw_data_payload, dict) else {}
                )
                ns.appointment_data = ns.appointment_data_raw if isinstance(ns.appointment_data_raw, dict) else {}
                ns.service_info = ns.appointment_data.get("service") or {}
                ns.service_name = (
                    ns.service_info.get("name", "unknown_service")
                    if isinstance(ns.service_info, dict)
                    else str(ns.service_info)
                )
                analytics.log_appointment(
                    user_id=ns.user_id,
                    service=ns.service_name,
                    status="booked",
                    messages_count=len(ns.current_context_messages or []),
                )
                try:
                    from services.session_rating_service import (
                        schedule_session_rating_prompt_after_booking,
                    )

                    asyncio.create_task(schedule_session_rating_prompt_after_booking(ns.user_id))
                except Exception as sr_e:
                    print(f"WARNING: session rating schedule (submit_booking_intent): {sr_e}")
            except Exception as an_sb:
                print(f"WARNING: analytics (submit_booking_intent): {an_sb}")
