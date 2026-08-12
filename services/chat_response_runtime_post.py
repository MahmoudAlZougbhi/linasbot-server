"""Post-tool booking recovery and reply guards."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    Any,
    _apply_inferred_name_from_user_bundle,
    _bot_reply_claims_completed_appointment_update,
    _bot_reply_claims_completed_booking,
    _extract_booking_args_from_gpt_raw,
    _extract_direct_submit_booking_args_from_user_message,
    _fix_misassigned_tattoo_service_for_hair_booking,
    _infer_service_id_from_leak,
    _normalize_arabic_reply,
    _prune_redundant_booking_questions_when_name_from_bundle,
    _record_tool_round_trip,
    _reply_from_submit_booking_tool,
    _safe_int,
    _try_recover_create_appointment_from_auxiliary_gpt_json,
    asyncio,
    config,
    json,
)


async def postprocess_chat_response(ns: Any) -> Any:
    if not ns.tool_calls and not ns.social_channel:
        ns.direct_submit_args = _extract_direct_submit_booking_args_from_user_message(
            ns.user_input,
            phone=ns.customer_phone_clean or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number") or ns.user_id,
            current_gender=ns.current_gender,
            fallback_name=config.user_names.get(ns.user_id, ns.user_name),
        )
        if ns.direct_submit_args:
            try:
                from services.booking.booking_fsm import mark_booking_completed
                from services.booking.booking_fsm import merge_patch as _fsm_merge_patch
                from services.booking.intent_pipeline import handle_submit_booking_intent

                _fsm_merge_patch(ns.user_id, {"confirmed_booking": True})
                ns.direct_output = await handle_submit_booking_intent(
                    user_id=ns.user_id,
                    phone=str(ns.direct_submit_args.get("phone") or "").strip(),
                    current_gender=ns.current_gender,
                    user_input=ns.user_input,
                    function_args=ns.direct_submit_args,
                )
                ns.direct_content = json.dumps(ns.direct_output, ensure_ascii=False, default=str)
                ns.tool_round_trips.append(
                    _record_tool_round_trip(
                        "submit_booking_intent_direct_from_user_message",
                        ns.direct_submit_args,
                        ns.direct_content,
                        ns.direct_output if isinstance(ns.direct_output, dict) else None,
                    )
                )
                ns.extra_tool_names.append("submit_booking_intent")
                ns.parsed_response["action"] = "answer_question"
                ns.parsed_response["bot_reply"] = _reply_from_submit_booking_tool(
                    ns.direct_output if isinstance(ns.direct_output, dict) else {},
                    ns.parsed_response.get("detected_language") or ns.current_preferred_lang,
                )
                if (
                    isinstance(ns.direct_output, dict)
                    and ns.direct_output.get("success")
                    and ns.direct_output.get("booking_flow_state") == "booked"
                ):
                    ns.recovered_create_appointment_ok = True
                    try:
                        mark_booking_completed(ns.user_id)
                    except Exception as _direct_mc_e:
                        print(f"⚠️ direct submit mark_booking_completed: {_direct_mc_e}")
            except Exception as direct_submit_e:
                print(f"⚠️ no-tool direct submit from user message failed: {direct_submit_e}")

    try:
        from services.booking import booking_fsm as _bfsm_patch

        if _bfsm_patch.fsm_enabled() and not ns.social_channel:
            ns._bp = ns.parsed_response.get("booking_fsm_patch")
            if isinstance(ns._bp, dict) and ns._bp:
                _bfsm_patch.merge_patch(ns.user_id, ns._bp)
        ns.parsed_response.pop("booking_fsm_patch", None)
    except Exception as _bfsm_patch_e:
        print(f"⚠️ booking_fsm_patch merge: {_bfsm_patch_e}")

    _apply_inferred_name_from_user_bundle(ns.user_id, ns.user_input, ns.parsed_response)
    _prune_redundant_booking_questions_when_name_from_bundle(ns.user_input, ns.parsed_response)

    # AI decides language - use AI's detected_language from response, fallback to pre-detected
    ns.bot_reply = ns.parsed_response.get("bot_reply", "")
    ns.ai_detected = ns.parsed_response.get("detected_language")
    ns.detected_language = ns.ai_detected if ns.ai_detected in ("ar", "en", "fr", "franco") else ns.current_preferred_lang
    ns.parsed_response["detected_language"] = ns.detected_language
    print(f"🌐 AI detected language: {ns.detected_language}")

    # Sanitize: when replying in Arabic/franco, replace Latin brand names with Arabic (no mixing)
    if ns.detected_language in ("ar", "franco") and ns.bot_reply:
        ns.bot_reply = _normalize_arabic_reply(ns.bot_reply)
        ns.parsed_response["bot_reply"] = ns.bot_reply

    try:
        from services.booking import booking_fsm as _bfsm_guard

        if _bfsm_guard.fsm_enabled() and not ns.social_channel:
            ns.br2, ns._gmeta = _bfsm_guard.guard_bot_reply_booking_identity(
                ns.user_id,
                ns.parsed_response.get("bot_reply") or "",
                ns.current_gender,
                lang=ns.detected_language,
            )
            if ns._gmeta.get("guard_applied"):
                ns.parsed_response["bot_reply"] = ns.br2
                ns.parsed_response["booking_reply_guard"] = ns._gmeta
    except Exception as _bg_e:
        print(f"⚠️ booking reply guard: {_bg_e}")

    # Ensure current_gender_from_config in the output reflects the *actual* config value
    # This is critical for GPT to "see" the current state of the bot's knowledge about gender.
    ns.parsed_response["current_gender_from_config"] = ns.current_gender

    # Respect AI decision: do not override action/bot_reply here.
    # We only normalize metadata fields above (detected_language/current_gender_from_config).

    # We allow GPT to detect gender and signal it, but also check for explicit detection for robustness
    # This part ensures that if our local gender recognition service detects a strong gender, it's reflected
    # in the output, potentially overriding GPT's 'null' or 'unknown' if it was less confident.
    if ns.explicitly_detected_gender_from_input and ns.explicitly_detected_gender_from_input in ["male", "female"]:
        ns.parsed_response["detected_gender"] = ns.explicitly_detected_gender_from_input
    elif "detected_gender" in ns.parsed_response and ns.parsed_response["detected_gender"] not in ["male", "female"]:
        # If GPT returned something like 'unknown' or 'null' for detected_gender, set it to None
        ns.parsed_response["detected_gender"] = None

    try:
        from services.booking import booking_fsm as _bfsm_lock_g

        ns._dg_final = ns.parsed_response.get("detected_gender")
        if (
            not ns.social_channel
            and _bfsm_lock_g.fsm_enabled()
            and ns._dg_final in ("male", "female")
            and (config.user_booking_state.get(ns.user_id) or {}).get("booking_fsm", {}).get("active")
        ):
            _bfsm_lock_g.lock_gender_from_session(ns.user_id, ns._dg_final, "model_output")
    except Exception as _lg_e:
        print(f"⚠️ booking_fsm lock gender (post-parse): {_lg_e}")

    if "action" not in ns.parsed_response or "bot_reply" not in ns.parsed_response:
        raise ValueError("GPT response missing required fields (action or bot_reply)")

    # Flow logging metadata for dashboard transparency (detailed for Activity Flow)
    ns.tool_names = (
        [getattr(getattr(ns.tc, "function", None), "name", "") for ns.tc in ns.tool_calls if getattr(ns.tc, "function", None)]
        if ns.tool_calls
        else []
    ) + ns.extra_tool_names
    ns._brl_flow = (ns.parsed_response.get("bot_reply") or "").strip().lower()
    ns.had_update_tool = bool(ns.tool_calls) and (
        "update_appointment_date" in ns.tool_names
        or "update_paused_appointment" in ns.tool_names
        or "edit_appointment" in ns.tool_names
        or "resume_appointment" in ns.tool_names
    )

    if (
        not ns.social_channel
        and ns.tool_calls
        and "submit_booking_intent" not in ns.tool_names
        and "create_appointment" not in ns.tool_names
        and not ns.api_failure_reason
    ):
        ns.direct_submit_args = _extract_direct_submit_booking_args_from_user_message(
            ns.user_input,
            phone=ns.customer_phone_clean or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number") or ns.user_id,
            current_gender=ns.current_gender,
            fallback_name=config.user_names.get(ns.user_id, ns.user_name),
        )
        if ns.direct_submit_args:
            try:
                from services.booking.booking_fsm import mark_booking_completed
                from services.booking.booking_fsm import merge_patch as _fsm_merge_patch
                from services.booking.intent_pipeline import handle_submit_booking_intent

                _fsm_merge_patch(ns.user_id, {"confirmed_booking": True})
                ns.direct_output = await handle_submit_booking_intent(
                    user_id=ns.user_id,
                    phone=str(ns.direct_submit_args.get("phone") or "").strip(),
                    current_gender=ns.current_gender,
                    user_input=ns.user_input,
                    function_args=ns.direct_submit_args,
                )
                ns.direct_content = json.dumps(ns.direct_output, ensure_ascii=False, default=str)
                ns.tool_round_trips.append(
                    _record_tool_round_trip(
                        "submit_booking_intent_direct_from_user_message",
                        ns.direct_submit_args,
                        ns.direct_content,
                        ns.direct_output if isinstance(ns.direct_output, dict) else None,
                    )
                )
                ns.tool_names.append("submit_booking_intent")
                ns.parsed_response["action"] = "answer_question"
                ns.parsed_response["bot_reply"] = _reply_from_submit_booking_tool(
                    ns.direct_output if isinstance(ns.direct_output, dict) else {},
                    ns.detected_language,
                )
                if (
                    isinstance(ns.direct_output, dict)
                    and ns.direct_output.get("success")
                    and ns.direct_output.get("booking_flow_state") == "booked"
                ):
                    ns.recovered_create_appointment_ok = True
                    try:
                        mark_booking_completed(ns.user_id)
                    except Exception as _direct_mc_e:
                        print(f"⚠️ direct submit mark_booking_completed: {_direct_mc_e}")
            except Exception as direct_submit_e:
                print(f"⚠️ direct submit from user message failed: {direct_submit_e}")

    ns._leaked_rec = _extract_booking_args_from_gpt_raw(ns.gpt_raw_content or "")
    ns._rec_has_date = bool(ns._leaked_rec.get("date") or ns._leaked_rec.get("date_components"))
    ns._rec_mach = _safe_int(ns._leaked_rec.get("machine_id"))
    ns._rec_lw = dict(ns._leaked_rec)
    _fix_misassigned_tattoo_service_for_hair_booking(ns._rec_lw, ns.current_gender, ns.user_input, ns.current_context_messages)
    ns._rec_sid = _safe_int(ns._rec_lw.get("service_id")) or _infer_service_id_from_leak(ns._leaked_rec, ns.current_gender)
    ns.stuck_hair_booking_recovery = (
        (ns.parsed_response.get("action") or "").strip().lower() == "ask_for_details_for_booking"
        and ns._rec_has_date
        and ns._rec_mach is not None
        and ns._rec_sid in LASER_HAIR_REMOVAL_SERVICE_IDS
    )

    # Model sometimes puts create_appointment-shaped JSON in the assistant text but only calls get_machines.
    if (
        not ns.social_channel
        and ns.tool_calls
        and "create_appointment" not in ns.tool_names
        and "submit_booking_intent" not in ns.tool_names
        and not ns.api_failure_reason
        and (
            (
                _bot_reply_claims_completed_booking(ns.parsed_response.get("bot_reply") or "")
                and not _bot_reply_claims_completed_appointment_update(ns.parsed_response.get("bot_reply") or "")
            )
            or ns.stuck_hair_booking_recovery
        )
    ):
        ns.rec_api = await _try_recover_create_appointment_from_auxiliary_gpt_json(
            ns.gpt_raw_content,
            user_id=ns.user_id,
            customer_phone_clean=ns.customer_phone_clean,
            current_gender=ns.current_gender,
            current_preferred_lang=ns.current_preferred_lang,
            current_context_messages=ns.current_context_messages,
            user_input=ns.user_input,
            body_part_required_service_ids=ns.body_part_required_service_ids,
            is_reschedule_intent=ns.is_reschedule_intent,
            tool_names_so_far=ns.tool_names,
        )
        if ns.rec_api is not None:
            ns.rec_dump = json.dumps(ns.rec_api, default=str)
            ns.tool_round_trips.append(
                _record_tool_round_trip(
                    "create_appointment_recovered_from_auxiliary_gpt_json",
                    {"note": "parsed from model output before action JSON", "recovered": True},
                    ns.rec_dump,
                    ns.rec_api if isinstance(ns.rec_api, dict) else None,
                )
            )
            if ns.rec_api.get("success") and ns.rec_api.get("booking_flow_state") == "booked":
                ns.recovered_create_appointment_ok = True
                if ns.stuck_hair_booking_recovery:
                    ns.parsed_response["action"] = "answer_question"
                    if ns.detected_language in ("ar", "franco"):
                        ns.parsed_response["bot_reply"] = _normalize_arabic_reply(
                            "تم تثبيت الحجز على السيستم. إذا بدك تعديل بالوقت أو الفرع، خبرني 🌷"
                        )
                    else:
                        ns.parsed_response["bot_reply"] = (
                            "Your appointment has been saved in the system. "
                            "Let me know if you need to change the time or branch."
                        )
                try:
                    from services.analytics_events import analytics

                    ns._rec_api = (
                        ns.rec_api.get("api_response") if isinstance(ns.rec_api.get("api_response"), dict) else ns.rec_api
                    )
                    ns.raw_data_payload = ns._rec_api.get("data", {}) if isinstance(ns._rec_api, dict) else {}
                    ns.appointment_data = (
                        ns.raw_data_payload.get("appointment") if isinstance(ns.raw_data_payload, dict) else {}
                    ) or {}
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
                        print(f"WARNING: session rating schedule (recovered booking): {sr_e}")
                except Exception as an_e:
                    print(f"WARNING: analytics (recovered create_appointment): {an_e}")
            else:
                ns._rec_fail = (
                    (ns.rec_api or {}).get("api_response")
                    if isinstance((ns.rec_api or {}).get("api_response"), dict)
                    else (ns.rec_api or {})
                )
                ns.err_msg_raw = (
                    ns._rec_fail.get("message")
                    if isinstance(ns._rec_fail, dict) and ns._rec_fail.get("message") is not None
                    else (ns.rec_api or {}).get("human_readable_reason", "Unknown error")
                )
                ns.err_msg = (
                    str(ns.err_msg_raw) if not isinstance(ns.err_msg_raw, dict) else json.dumps(ns.err_msg_raw, default=str)
                )
                ns.api_failure_reason = f"create_appointment_tool_failed: {ns.err_msg}"
