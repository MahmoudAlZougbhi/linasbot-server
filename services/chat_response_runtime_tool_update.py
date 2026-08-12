"""update/resume/edit appointment tool-arg guards."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    LOOP_CONTINUE,
    Any,
    _appointment_numeric_id,
    _ordered_paused_appointments_from_snapshot,
    _record_tool_round_trip,
    _resolve_machine_for_booking,
    _resolve_user_chosen_paused_appointment_id,
    _safe_int,
    _status_requests_available,
    _user_explicitly_requests_machine_change,
    _user_intent_resume_paused_appointment,
    api_integrations,
    config,
    extract_appointment_booking_fields,
    find_appointment_row_in_check_next_payload,
    json,
)


async def handle_update_appointment_tools(ns: Any) -> Any:
    if ns.function_name in (
        "update_appointment_date",
        "update_paused_appointment",
        "edit_appointment",
        "resume_appointment",
    ):
        ns.phone_for_pause_guard = ns.normalize_phone_for_lookup(
            ns.function_args.get("phone")
            or ns.customer_phone_clean
            or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
            or ns.user_id
        )

        if ns.user_requested_change and ns.phone_for_pause_guard:
            ns.paused_appointment_id = await ns.find_paused_appointment_id(ns.phone_for_pause_guard)
            ns._next_pl_upd = (
                ns.extract_check_next_appointment(ns.check_next_appointment_result)
                if ns.check_next_appointment_result
                else {}
            )
            ns._next_id_upd = ns.extract_appointment_id(ns._next_pl_upd)
            ns._next_st_upd = ns.extract_appointment_status(ns._next_pl_upd)
            # Only force paused id when the system's NEXT row is that paused appointment.
            # If next is Active/Available, rescheduling must target that id — not an older paused record.
            if (
                ns.paused_appointment_id
                and ns.check_next_appointment_result
                and ns._next_id_upd is not None
                and ns._next_id_upd == ns.paused_appointment_id
                and ns.is_paused_status(ns._next_st_upd)
            ):
                try:
                    ns.gpt_aid_int = _safe_int(ns.function_args.get("appointment_id"))
                except (TypeError, ValueError):
                    ns.gpt_aid_int = None
                if ns.gpt_aid_int != ns.paused_appointment_id:
                    print(
                        f"SAFETY: Overriding {ns.function_name} appointment_id with paused NEXT appointment_id={ns.paused_appointment_id}"
                    )
                    ns.function_args["appointment_id"] = ns.paused_appointment_id
                    ns.forced_update_appointment_id = ns.paused_appointment_id

        # When "next" from check_next is an active/Available row but the file has exactly ONE
        # paused row and the user wording is "resume / lift from pause", the model often chains
        # appointment_id to the active row — CRM then never moves the paused row.
        if (
            ns.user_requested_change
            and ns.phone_for_pause_guard
            and not ns.forced_update_appointment_id
            and _user_intent_resume_paused_appointment(ns.user_input)
        ):
            ns.paused_rows = await ns.list_paused_appointment_ids(ns.phone_for_pause_guard)
            if len(ns.paused_rows) == 1:
                ns.single_paused = ns.paused_rows[0]
                ns._next_pl_mix = (
                    ns.extract_check_next_appointment(ns.check_next_appointment_result)
                    if ns.check_next_appointment_result
                    else {}
                )
                ns._next_id_mix = ns.extract_appointment_id(ns._next_pl_mix)
                ns._next_st_mix = ns.extract_appointment_status(ns._next_pl_mix)
                if ns._next_id_mix is not None and not ns.is_paused_status(ns._next_st_mix):
                    try:
                        ns.gpt_aid_mix = _safe_int(ns.function_args.get("appointment_id"))
                    except (TypeError, ValueError):
                        ns.gpt_aid_mix = None
                    if ns.gpt_aid_mix is None or ns.gpt_aid_mix == ns._next_id_mix:
                        print(
                            f"SAFETY: Next appointment is active id={ns._next_id_mix} but user resumes "
                            f"single paused id={ns.single_paused} — overriding {ns.function_name}"
                        )
                        ns.function_args["appointment_id"] = ns.single_paused
                        ns.forced_update_appointment_id = ns.single_paused

        # Many paused rows: user picks "3" / "رقم 5" / pastes CRM id — model often passes wrong id or chains "next".
        # Do not require user_requested_change: a lone "3" after a numbered list is not detected as reschedule text.
        if ns.phone_for_pause_guard and not ns.forced_update_appointment_id:
            ns.paused_order = _ordered_paused_appointments_from_snapshot(ns.check_next_appointment_result)
            if len(ns.paused_order) < 2:
                try:
                    ns.ph = ns.normalize_phone_for_lookup(ns.phone_for_pause_guard) or ns.phone_for_pause_guard
                    ns.fresh_apts = await api_integrations.get_customer_appointments(phone=ns.ph)
                    if isinstance(ns.fresh_apts, dict) and ns.fresh_apts.get("success"):
                        ns.paused_order = _ordered_paused_appointments_from_snapshot(ns.fresh_apts)
                except Exception as multi_pause_e:
                    print(f"WARNING: multi-paused pick: get_customer_appointments refresh failed: {multi_pause_e}")
            if len(ns.paused_order) >= 2:
                ns.pids = [
                    ns.x for ns.x in (_appointment_numeric_id(ns.r) for ns.r in ns.paused_order) if ns.x is not None
                ]
                ns.chosen_pid = _resolve_user_chosen_paused_appointment_id(ns.user_input, ns.pids)
                if ns.chosen_pid is not None:
                    try:
                        ns.gpt_aid_pick = _safe_int(ns.function_args.get("appointment_id"))
                    except (TypeError, ValueError):
                        ns.gpt_aid_pick = None
                    if ns.gpt_aid_pick is None or ns.gpt_aid_pick != ns.chosen_pid:
                        print(
                            f"SAFETY: {len(ns.pids)} paused rows: user choice -> appointment_id={ns.chosen_pid} "
                            f"(gpt had {ns.gpt_aid_pick})"
                        )
                        ns.function_args["appointment_id"] = ns.chosen_pid
                        ns.forced_update_appointment_id = ns.chosen_pid

        if ns.phone_for_pause_guard and not ns.function_args.get("phone"):
            ns.function_args["phone"] = ns.phone_for_pause_guard

        # Direct resume must never auto-chain to an active next appointment id.
        if (
            ns.function_name == "resume_appointment"
            and ns.check_next_appointment_result
            and not ns.forced_update_appointment_id
        ):
            ns._next_pl_resume = ns.extract_check_next_appointment(ns.check_next_appointment_result)
            ns._next_id_resume = ns.extract_appointment_id(ns._next_pl_resume)
            ns._next_st_resume = ns.extract_appointment_status(ns._next_pl_resume)
            if ns._next_id_resume is not None and ns.is_paused_status(ns._next_st_resume):
                try:
                    ns.gpt_aid_resume = _safe_int(ns.function_args.get("appointment_id"))
                except (TypeError, ValueError):
                    ns.gpt_aid_resume = None
                if ns.gpt_aid_resume is None:
                    print(f"DEBUG: Auto-chaining paused NEXT appointment_id for resume -> {ns._next_id_resume}")
                    ns.function_args["appointment_id"] = ns._next_id_resume
                    ns.forced_update_appointment_id = ns._next_id_resume

        ns.aid_for_machine = _safe_int(ns.function_args.get("appointment_id"))
        ns.machine_row = (
            find_appointment_row_in_check_next_payload(ns.check_next_appointment_result, ns.aid_for_machine)
            if ns.aid_for_machine is not None and ns.check_next_appointment_result
            else None
        )
        ns.row_service_id = ns.row_branch_id = ns.row_machine_id = None
        if ns.machine_row is not None:
            ns.row_service_id, ns.row_branch_id, ns.row_machine_id = extract_appointment_booking_fields(ns.machine_row)
        ns.target_row_was_paused = False
        if ns.machine_row is not None:
            ns.target_row_was_paused = ns.is_paused_status(ns.extract_appointment_status(ns.machine_row))
        elif ns.forced_update_appointment_id is not None:
            ns.target_row_was_paused = True
        if ns.target_row_was_paused and ns.function_name in (
            "update_appointment_date",
            "update_paused_appointment",
            "edit_appointment",
            "resume_appointment",
        ):
            if ns.function_name == "update_appointment_date":
                ns.paused_followup_available_action_requested = True
            elif ns.function_name == "update_paused_appointment":
                if _status_requests_available(ns.function_args.get("status")):
                    ns.paused_followup_available_action_requested = True
            elif ns.function_name == "resume_appointment":
                ns.paused_followup_available_action_requested = True
        ns.requested_machine_change = _user_explicitly_requests_machine_change(ns.all_user_text_for_date)
        ns.arg_machine_id = _safe_int(ns.function_args.get("machine_id"))
        if ns.arg_machine_id is not None and not ns.requested_machine_change:
            print(
                "SAFETY: Removing unrequested machine_id from appointment update "
                f"(appointment_id={ns.aid_for_machine}, machine_id={ns.arg_machine_id})"
            )
            ns.function_args.pop("machine_id", None)
        elif ns.arg_machine_id is not None:
            ns.resolved_machine_id = await _resolve_machine_for_booking(
                _safe_int(ns.function_args.get("service_id")) or ns.row_service_id,
                ns.arg_machine_id,
                preferred_existing_machine_id=ns.row_machine_id,
            )
            if ns.resolved_machine_id is not None:
                ns.function_args["machine_id"] = ns.resolved_machine_id
            else:
                ns.function_args.pop("machine_id", None)

        ns.requires_date = (
            ns.function_name == "update_appointment_date"
            or (ns.function_name == "update_paused_appointment" and "date" in ns.function_args)
            or (ns.function_name == "edit_appointment" and "date" in ns.function_args)
        )
        if ns.requires_date:
            if not ns.normalize_tool_date(
                ns.function_name,
                ns.function_args,
                user_input_for_date=ns.user_input,
                context_messages_for_date=ns.current_context_messages,
            ):
                ns.err_content = json.dumps(
                    {
                        "success": False,
                        "message": "Reschedule date validation failed; structured date/date_components required from AI.",
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
                return LOOP_CONTINUE
