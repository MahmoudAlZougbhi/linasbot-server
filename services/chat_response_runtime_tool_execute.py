"""Dispatch remaining tools through api_integrations."""

from __future__ import annotations

from services.chat_response_runtime_common import (
    Any,
    _extract_customer_appointments_list,
    _finalize_create_appointment_payload_for_api,
    _record_tool_round_trip,
    api_integrations,
    asyncio,
    cast,
    config,
    json,
)


async def handle_execute_api_tool(ns: Any) -> Any:
    if ns.function_name in ("retrieve_relevant_knowledge", "submit_booking_intent"):
        return None
    if hasattr(api_integrations, ns.function_name) and callable(getattr(api_integrations, ns.function_name)):
        ns.function_to_call = getattr(api_integrations, ns.function_name)
        print(f"DEBUG: Executing tool: {ns.function_name} with args: {ns.function_args}")

        try:
            if ns.function_name == "create_appointment":
                _finalize_create_appointment_payload_for_api(ns.function_args)
                from services.booking.intent_pipeline import legacy_create_appointment_tool_output

                ns.tool_output = await legacy_create_appointment_tool_output(
                    user_id=ns.user_id,
                    function_args=ns.function_args,
                    current_gender=ns.current_gender,
                    user_input=ns.user_input,
                )
            else:
                ns.tool_output = await ns.function_to_call(**ns.function_args)
            if (
                ns.function_name == "get_body_parts"
                and isinstance(ns.tool_output, dict)
                and not ns.tool_output.get("success")
            ):
                ns.tool_output = dict(ns.tool_output)
                ns.tool_output["hint_for_model"] = (
                    "CRM body-part list failed to load. Do NOT ask the user for 'the area name as registered in the system' "
                    "when they already described the location (e.g. neck / رقبة / ra2be). "
                    "Call submit_booking_intent with body_part set to their wording and body_part_ids empty when possible "
                    "so the server resolves IDs, or briefly apologize and offer branch contact if resolution is impossible. "
                    "Ops: Appointment API uses GET /service/data for areas (LINASLASER_SERVICE_DATA_PATH); "
                    "legacy hosts may set LINASLASER_GET_BODY_PARTS_PATH or LINASLASER_TATTOO_BODY_SYNONYMS_JSON."
                )
            if (
                ns.function_name in ("update_appointment_date", "update_paused_appointment")
                and isinstance(ns.tool_output, dict)
                and ns.tool_output.get("success")
            ):
                ns.tool_output = dict(ns.tool_output)
                ns.ra_raw = ns.tool_output.get("resume_appointment") or {}
                ns.ra = ns.ra_raw if isinstance(ns.ra_raw, dict) else {}
                if ns.ra.get("attempted"):
                    ns.pause_resume_attempted = True
                ns.base = "This tool returned success — the Agent API accepted the new datetime (see data.old_date / new_date). "
                if ns.ra.get("attempted") and ns.ra.get("success"):
                    ns._pause_resume_confirmed_via_date_update = True
                    ns.base += (
                        "A follow-up **resume** call also succeeded — the CRM should show the slot as active/Available "
                        "(not Paused) in addition to the new time. Say so briefly in Arabic if bot_reply is Arabic. "
                    )
                elif ns.ra.get("attempted") and not ns.ra.get("success"):
                    ns.base += (
                        f"A follow-up **resume** call was attempted ({ns.ra.get('path')!r}) but failed: {ns.ra.get('message')!r}. "
                        "Datetime was still updated. If status still shows «موقوف», ask reception to clear pause or fix the resume endpoint; "
                        "do not claim the datetime change failed. "
                    )
                elif ns.ra.get("skipped"):
                    ns.base += (
                        "Follow-up Paused→Available (update-status) was skipped by the server. "
                        "If the row stays Paused in the CRM, ask backend/reception to verify POST /api/appointments/update-status. "
                    )
                else:
                    ns.base += (
                        "If the customer says the clinic computer still shows the old time: explain that the booking API "
                        "confirmed the update; reception software may need refresh; rows can still show «موقوف» while "
                        "the time field was updated—staff can verify by appointment_id. "
                    )
                ns.base += "Do not claim the update failed unless a later tool result contradicts this."
                ns.tool_output["hint_for_model"] = ns.base
            if ns.function_name == "resume_appointment" and isinstance(ns.tool_output, dict):
                ns.pause_resume_attempted = True
                ns.tool_output = dict(ns.tool_output)
                if ns.tool_output.get("success"):
                    ns.direct_resume_success = True
                    ns.tool_output["hint_for_model"] = (
                        "This tool returned success — the paused appointment was restored to active/Available "
                        "without changing the slot. You may say the appointment is active again."
                    )
                else:
                    ns.tool_output["hint_for_model"] = (
                        "Resume was requested but this tool did not confirm success. "
                        "Do NOT say the appointment became Available. If needed, say the request did not complete and staff may need to verify it."
                    )
            print(f"DEBUG: Tool output for {ns.function_name}: {ns.tool_output}")

            # Enrich "next" with full customer list so the model can list every upcoming booking.
            if (
                ns.function_name == "check_next_appointment"
                and isinstance(ns.tool_output, dict)
                and ns.tool_output.get("success")
            ):
                ns.phone_for_enrich = ns.normalize_phone_for_lookup(
                    ns.function_args.get("phone")
                    or ns.customer_phone_clean
                    or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
                    or ns.user_id
                )
                if ns.phone_for_enrich:
                    try:
                        ns.list_resp = await api_integrations.get_customer_appointments(phone=ns.phone_for_enrich)
                        if isinstance(ns.list_resp, dict) and ns.list_resp.get("success"):
                            ns.all_apts = _extract_customer_appointments_list(ns.list_resp)
                            if ns.all_apts:
                                ns.d = ns.tool_output.get("data")
                                if isinstance(ns.d, dict):
                                    ns.d["customer_appointments"] = ns.all_apts
                                elif ns.d is None:
                                    ns.tool_output["data"] = {"customer_appointments": ns.all_apts}
                                else:
                                    # Keep original data shape for appointment_id extraction; list is parallel.
                                    ns.tool_output["customer_appointments"] = ns.all_apts
                                print(
                                    f"DEBUG: check_next_appointment enriched with {len(ns.all_apts)} customer_appointments"
                                )
                    except Exception as enrich_e:
                        print(f"WARNING: check_next_appointment enrich get_customer_appointments failed: {enrich_e}")
                ns.check_next_appointment_result = ns.tool_output
                print("DEBUG: Stored check_next_appointment result for auto-chaining")

            # 📊 ANALYTICS: Track service when appointment is created
            if (
                ns.function_name == "create_appointment"
                and isinstance(ns.tool_output, dict)
                and ns.tool_output.get("success")
            ):
                from services.analytics_events import analytics

                ns.create_api_wrapped: dict[str, Any] = (
                    cast(dict[str, Any], ns.tool_output.get("api_response"))
                    if isinstance(ns.tool_output.get("api_response"), dict)
                    else ns.tool_output
                )
                ns.raw_data_payload = (
                    ns.create_api_wrapped.get("data", {}) if isinstance(ns.create_api_wrapped, dict) else {}
                )
                if isinstance(ns.raw_data_payload, dict):
                    ns.create_appointment_data: dict[str, Any] = ns.raw_data_payload.get("appointment") or {}
                    ns.pricing_from_appointment = (
                        ns.raw_data_payload.get("pricing")
                        or ns.create_appointment_data.get("pricing")
                        or ns.create_appointment_data.get("price_details")
                    )
                else:
                    ns.create_appointment_data = {}
                    ns.pricing_from_appointment = None
                if ns.pricing_from_appointment:
                    ns.latest_pricing_payload = ns.pricing_from_appointment
                    config.user_booking_state[ns.user_id]["last_pricing_payload"] = ns.pricing_from_appointment
                    print("💰 Synced pricing payload captured from create_appointment")
                ns.service_info = ns.create_appointment_data.get("service") or {}
                ns.service_name = (
                    ns.service_info.get("name", "unknown_service")
                    if isinstance(ns.service_info, dict)
                    else str(ns.service_info)
                )
                ns.machine_info = ns.create_appointment_data.get("machine")
                # Handle machine being either a string or a dict
                ns.machine_name = (
                    ns.machine_info.get("name", "unassigned")
                    if isinstance(ns.machine_info, dict)
                    else (str(ns.machine_info) if ns.machine_info else "unassigned")
                )

                print(f"📊 Analytics: Service tracked from appointment - {ns.service_name}, Machine: {ns.machine_name}")

                # Log appointment booking
                analytics.log_appointment(
                    user_id=ns.user_id,
                    service=ns.service_name,
                    status="booked",
                    messages_count=len(ns.current_context_messages),
                )
                print(f"📊 Analytics: Appointment booked - {ns.service_name}")
                try:
                    from services.session_rating_service import (
                        schedule_session_rating_prompt_after_booking,
                    )

                    asyncio.create_task(schedule_session_rating_prompt_after_booking(ns.user_id))
                except Exception as sr_e:
                    print(f"WARNING: session rating schedule (create_appointment): {sr_e}")
                if ns.tool_output.get("booking_flow_state") == "booked":
                    ns.recovered_create_appointment_ok = True
            elif (
                ns.function_name == "create_appointment"
                and isinstance(ns.tool_output, dict)
                and not ns.tool_output.get("success")
            ):
                ns._api = (
                    ns.tool_output.get("api_response") if isinstance(ns.tool_output.get("api_response"), dict) else {}
                )
                ns.err_msg_raw = (
                    ns._api.get("message")
                    if isinstance(ns._api, dict) and ns._api.get("message") is not None
                    else ns.tool_output.get("human_readable_reason", "Unknown error")
                )
                ns.err_msg = (
                    str(ns.err_msg_raw)
                    if not isinstance(ns.err_msg_raw, dict)
                    else json.dumps(ns.err_msg_raw, default=str)
                )
                if ns.tool_output.get("error_type") == "validation_error":
                    print(f"create_appointment tool: validation failed (no handover): {ns.err_msg}")
                else:
                    ns.api_failure_reason = f"create_appointment_tool_failed: {ns.err_msg}"
                print(f"create_appointment tool: API failed (no user-text retry): {ns.err_msg}")

            # 📊 ANALYTICS: Track appointment reschedule
            elif (
                ns.function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment")
                and isinstance(ns.tool_output, dict)
                and ns.tool_output.get("success")
            ):
                ns.update_appointment_date_success_count += 1
                if ns.target_row_was_paused:
                    ns.paused_followup_update_succeeded = True
                from services.analytics_events import analytics

                # Get service from appointment data if available
                ns.update_appointment_data: dict[str, Any] = cast(dict[str, Any], ns.tool_output.get("data", {}))
                ns.service_id = ns.update_appointment_data.get("service_id")

                ns.service_map = {
                    1: "laser_hair_removal",
                    2: "tattoo_removal",
                    3: "co2_laser",
                    4: "skin_whitening",
                    5: "botox",
                    6: "fillers",
                }
                ns.service_name = (
                    ns.service_map.get(ns.service_id, "unknown_service") if ns.service_id else "unknown_service"
                )

                # Log appointment reschedule
                ns._aid_rs = ns.function_args.get("appointment_id")
                ns._ph_rs = (
                    ns.function_args.get("phone")
                    or ns.customer_phone_clean
                    or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
                    or ""
                )
                analytics.log_appointment(
                    user_id=ns.user_id,
                    service=ns.service_name,
                    status="rescheduled",
                    messages_count=0,
                    phone=str(ns._ph_rs).strip() if ns._ph_rs else None,
                    appointment_id=ns._aid_rs,
                )
                print(f"📊 Analytics: Appointment rescheduled - {ns.service_name}")
                ns.ra_raw = ns.tool_output.get("resume_appointment") or {}
                ns.ra = ns.ra_raw if isinstance(ns.ra_raw, dict) else {}
                if ns.ra.get("attempted") and ns.ra.get("success"):
                    ns.pause_resume_success_count += 1
                    try:
                        ns.aid = ns.function_args.get("appointment_id")
                        ns.phone_arg = (
                            ns.function_args.get("phone")
                            or ns.customer_phone_clean
                            or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
                            or ""
                        )
                        analytics.log_appointment_pause_cleared(
                            user_id=ns.user_id,
                            appointment_id=ns.aid,
                            phone=str(ns.phone_arg).strip() if ns.phone_arg else None,
                            service=ns.service_name,
                        )
                    except Exception as pr_e:
                        print(f"WARNING: analytics pause_cleared: {pr_e}")
            elif (
                ns.function_name == "resume_appointment"
                and isinstance(ns.tool_output, dict)
                and ns.tool_output.get("success")
            ):
                ns.pause_resume_success_count += 1
                ns.direct_resume_success = True
                if ns.target_row_was_paused:
                    ns.paused_followup_update_succeeded = True
            elif (
                ns.function_name in ("update_appointment_date", "update_paused_appointment", "edit_appointment")
                and isinstance(ns.tool_output, dict)
                and not ns.tool_output.get("success")
            ):
                ns.err_msg_raw = (ns.tool_output or {}).get("message", "Unknown error")
                ns.err_msg = (
                    str(ns.err_msg_raw)
                    if not isinstance(ns.err_msg_raw, dict)
                    else json.dumps(ns.err_msg_raw, default=str)
                )
                ns.api_failure_reason = f"update_appointment_date_tool_failed: {ns.err_msg}"
                print(f"update_appointment_date tool: API failed: {ns.err_msg}")

            ns.tool_content = json.dumps(ns.tool_output, default=str)
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
        except Exception as tool_e:
            ns.api_failure_reason = f"tool_execution_error:{ns.function_name}: {tool_e}"
            print(f"â‌Œ ERROR executing tool {ns.function_name}: {tool_e}")
            ns.err_content = json.dumps({"success": False, "message": f"Error executing tool: {tool_e}"})
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
    else:
        ns.api_failure_reason = f"tool_not_found:{ns.function_name}"
        print(f"â‌Œ ERROR: Tool function '{ns.function_name}' not found in api_integrations.")
        ns.err_content = json.dumps(
            {"success": False, "message": f"Tool function '{ns.function_name}' not implemented."}
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
