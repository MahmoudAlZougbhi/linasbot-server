"""create_appointment: customer ensure + payload."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    LOOP_CONTINUE,
    Any,
    _coerce_body_part_ids_from_gpt_booking_args,
    _normalize_body_part_ids,
    _record_tool_round_trip,
    _remember_booking_selection,
    _resolve_machine_for_booking,
    _safe_int,
    _try_infer_body_part_ids_from_conversation,
    api_integrations,
    config,
    json,
    re,
)


async def handle_create_appointment_payload(ns: Any) -> Any:
    if ns.function_name == "create_appointment":
        ns.function_args["phone"] = ns.phone_number  # Use the extracted/stored phone number

        # Check if customer exists, if not, create them
        ns.customer_exists = False
        ns.customer_gender_for_api = ns.current_gender  # Default to current gender
        if ns.customer_gender_for_api == "unknown":
            # Attempt to infer from name if needed for create_customer
            if ns.customer_name:
                # This is a very basic heuristic; a dedicated service would be better
                if ns.current_preferred_lang == "ar" or ns.current_preferred_lang == "franco":
                    if re.search(
                        r"\b(ظ…ط­ظ…ظˆط¯|ظ…ط­ظ…ط¯|ط¹ظ„ظٹ|ط£ط­ظ…ط¯|ط®ط§ظ„ط¯|ط±ط¬ظ„|ط´ط¨|ط°ظƒط±)\b",
                        ns.customer_name,
                        re.UNICODE,
                    ):
                        ns.customer_gender_for_api = "male"
                    elif re.search(
                        r"\b(ظ„ظٹظ†ط§|ظپط§ط·ظ…ط©|ظ…ط±ظٹظ…|ط³ط§ط±ط©|ط¨ظ†طھ|طµط¨ظٹط©|ط£ظ†ط«ظ‰)\b",
                        ns.customer_name,
                        re.UNICODE,
                    ):
                        ns.customer_gender_for_api = "female"
                elif ns.current_preferred_lang == "en":
                    if re.search(r"\b(john|paul|male|boy)\b", ns.customer_name, re.IGNORECASE):
                        ns.customer_gender_for_api = "male"
                    elif re.search(r"\b(jane|mary|female|girl)\b", ns.customer_name, re.IGNORECASE):
                        ns.customer_gender_for_api = "female"

            if ns.customer_gender_for_api == "unknown":
                ns.customer_gender_for_api = (
                    "male"  # Default to male if still unknown, adjust as clinic policy
                )

        # Ensure gender is in "Male" or "Female" format as required by API
        if ns.customer_gender_for_api:
            ns.customer_gender_for_api = ns.customer_gender_for_api.capitalize()  # "male" -> "Male"

        if ns.phone_number:
            ns.customer_check_response = await api_integrations.get_customer_by_phone(
                phone=ns.phone_number
            )  # NEW API call
            if (
                ns.customer_check_response
                and ns.customer_check_response.get("success")
                and ns.customer_check_response.get("data")
            ):
                ns.customer_exists = True
                print(f"DEBUG: Customer {ns.phone_number} found in API.")
            else:
                print(f"DEBUG: Customer {ns.phone_number} not found in API. Attempting to create.")
                if ns.customer_name and ns.customer_gender_for_api:
                    ns.create_customer_response = await api_integrations.create_customer(
                        name=ns.customer_name,
                        phone=ns.phone_number,
                        gender=ns.customer_gender_for_api,  # Pass as "Male" or "Female"
                        branch_id=config.DEFAULT_BRANCH_ID,  # NEW: Ensure branch_id is passed for customer creation
                    )
                    if ns.create_customer_response and ns.create_customer_response.get("success"):
                        ns.customer_exists = True
                        print(f"DEBUG: Successfully created new customer {ns.customer_name} in API.")
                    else:
                        print(
                            f"ERROR: Failed to create customer {ns.customer_name}: {ns.create_customer_response.get('message', 'Unknown error')}"
                        )
                        ns.err_content = json.dumps(
                            {
                                "success": False,
                                "message": f"Failed to create customer: {ns.create_customer_response.get('message', 'Unknown error')}",
                            }
                        )
                        ns.tool_round_trips.append(
                            _record_tool_round_trip("create_customer", ns.function_args, ns.err_content, None)
                        )
                        ns.messages.append(
                            {
                                "tool_call_id": ns.tool_call.id,
                                "role": "tool",
                                "name": "create_customer_failed",
                                "content": ns.err_content,
                            }
                        )
                        # Indicate that booking failed because customer creation failed
                        ns.parsed_response = {
                            "action": "ask_for_details_for_booking",  # Keep asking for details or suggest human handover
                            "bot_reply": "ط¹ط°ط±ظ‹ط§طŒ ظˆط§ط¬ظ‡طھ ظ…ط´ظƒظ„ط© ظپظٹ طھط³ط¬ظٹظ„ ط¨ظٹط§ظ†ط§طھظƒ ظƒط¹ظ…ظٹظ„ ط¬ط¯ظٹط¯. ظٹط±ط¬ظ‰ ط§ظ„طھط£ظƒط¯ ظ…ظ† طµط­ط© ط§ظ„ط§ط³ظ… ظˆط±ظ‚ظ… ط§ظ„ظ‡ط§طھظپطŒ ط£ظˆ ظٹظ…ظƒظ†ظ†ظٹ طھط­ظˆظٹظ„ظƒ ظ„ظ…ظˆط¸ظپ ظ„ظ…ط³ط§ط¹ط¯طھظƒ.",
                            "detected_language": ns.current_preferred_lang,
                            "detected_gender": ns.current_gender,
                            "current_gender_from_config": ns.current_gender,
                        }
                        ns.parsed_response["_flow_meta"] = {
                            "ai_first_response": ns.gpt_raw_content[:1500] if ns.gpt_raw_content else None,
                            "tool_round_trips": ns.tool_round_trips,
                            "tool_calls": ["create_customer"],
                        }
                        return ns.parsed_response
                else:
                    print("WARNING: Cannot create customer, missing name or gender.")
                    # Use language-specific error messages
                    ns.error_messages = {
                        "ar": f"ظ„ط£طھظ…ظƒظ† ظ…ظ† ط­ط¬ط² ظ…ظˆط¹ط¯ظƒطŒ ط£ط­طھط§ط¬ ظ„ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„{'.' if ns.current_gender != 'unknown' else ' ظˆط¬ظ†ط³ظƒ (ط´ط¨ ط£ظˆ طµط¨ظٹط©).'}",
                        "en": f"To book your appointment, I need your full name{'.' if ns.current_gender != 'unknown' else ' and gender (male or female).'}",
                        "fr": f"Pour rأ©server votre rendez-vous, j'ai besoin de votre nom complet{'.' if ns.current_gender != 'unknown' else ' et votre sexe (homme ou femme).'}",
                        "franco": f"ظ„ط­ط¬ط² ظ…ظˆط¹ط¯ظƒطŒ ط¨ط¯ظٹ ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„{'.' if ns.current_gender != 'unknown' else ' ظˆط¬ظ†ط³ظƒ (ط´ط¨ ط£ظˆ طµط¨ظٹط©).'}",
                    }
                    ns.parsed_response = {
                        "action": "ask_for_details_for_booking",
                        "bot_reply": ns.error_messages.get(ns.current_preferred_lang, ns.error_messages["en"]),
                        "detected_language": ns.current_preferred_lang,
                        "detected_gender": ns.current_gender,
                        "current_gender_from_config": ns.current_gender,
                    }
                    return ns.parsed_response
        else:
            print("WARNING: Cannot check or create customer, phone number not found.")
            # This should rarely happen since phone_number = user_id (WhatsApp ID)
            ns.error_messages = {
                "ar": "ط¹ط°ط±ط§ظ‹طŒ ط­ط¯ط«طھ ظ…ط´ظƒظ„ط© ظپظٹ ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط±ظ‚ظ… ظ‡ط§طھظپظƒ. ظٹط±ط¬ظ‰ ط§ظ„ظ…ط­ط§ظˆظ„ط© ظ…ط±ط© ط£ط®ط±ظ‰.",
                "en": "Sorry, there was an issue verifying your phone number. Please try again.",
                "fr": "Dأ©solأ©, il y a eu un problأ¨me pour vأ©rifier votre numأ©ro de tأ©lأ©phone. Veuillez rأ©essayer.",
                "franco": "ط¹ط°ط±ط§ظ‹طŒ ظپظٹ ظ…ط´ظƒظ„ط© ط¨ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط±ظ‚ظ… طھظ„ظپظˆظ†ظƒ. ط¬ط±ط¨ ظ…ط±ط© طھط§ظ†ظٹط©.",
            }
            ns.parsed_response = {
                "action": "ask_for_details_for_booking",
                "bot_reply": ns.error_messages.get(ns.current_preferred_lang, ns.error_messages["en"]),
                "detected_language": ns.current_preferred_lang,
                "detected_gender": ns.current_gender,
                "current_gender_from_config": ns.current_gender,
            }
            return ns.parsed_response

        # Only proceed to create_appointment if customer_exists is True
        if not ns.customer_exists:
            # This should ideally not be reached if previous logic is sound
            print("ERROR: Customer not created/found, cannot proceed with appointment.")
            ns.parsed_response = {
                "action": "human_handover",
                "bot_reply": "ط¹ط°ط±ظ‹ط§طŒ ظ„ط§ ظٹظ…ظƒظ†ظ†ظٹ ط¥طھظ…ط§ظ… ط§ظ„ط­ط¬ط² ط­ط§ظ„ظٹظ‹ط§. ط³ط£ظ‚ظˆظ… ط¨طھط­ظˆظٹظ„ظƒ ط¥ظ„ظ‰ ط£ط­ط¯ ظ…ظˆط¸ظپظٹظ†ط§ ظ„ظ„ظ…ط³ط§ط¹ط¯ط©.",
                "detected_language": ns.current_preferred_lang,
                "detected_gender": ns.current_gender,
                "current_gender_from_config": ns.current_gender,
            }
            return ns.parsed_response

        ns._legacy_inf = getattr(config, "BOOKING_LEGACY_INFERENCE", False)
        if ns._legacy_inf:
            # Legacy: default ids + area-name coercion + conversation inference for body parts
            ns.function_args["service_id"] = ns.function_args.get("service_id", config.DEFAULT_SERVICE_ID)
            ns.function_args["machine_id"] = ns.function_args.get("machine_id", config.DEFAULT_MACHINE_ID)
            ns.function_args["branch_id"] = ns.function_args.get("branch_id", config.DEFAULT_BRANCH_ID)
            _remember_booking_selection(ns.user_id, ns.function_args)

        ns.selected_service_id = _safe_int(ns.function_args.get("service_id"))
        if ns.selected_service_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
            ns.function_args["machine_id"] = await _resolve_machine_for_booking(
                ns.selected_service_id, _safe_int(ns.function_args.get("machine_id"))
            )
        else:
            ns.function_args.pop("machine_id", None)
            ns.function_args.pop("machine_name", None)
        _remember_booking_selection(ns.user_id, ns.function_args)

        if ns._legacy_inf:
            ns.sid_for_coerce = (
                ns.selected_service_id
                if ns.selected_service_id is not None
                else _safe_int(config.DEFAULT_SERVICE_ID)
            )
            ns.coerced_bp = await _coerce_body_part_ids_from_gpt_booking_args(
                ns.function_args,
                ns.sid_for_coerce if ns.sid_for_coerce is not None else 1,
                _safe_int(ns.function_args.get("machine_id")),
            )
            if ns.coerced_bp:
                ns.function_args["body_part_ids"] = ns.coerced_bp
                _remember_booking_selection(ns.user_id, ns.function_args)

        # If the model passed body_parts_with_sessions, normalize and align body_part_ids.
        ns.bps_raw = ns.function_args.get("body_parts_with_sessions")
        if isinstance(ns.bps_raw, list) and ns.bps_raw:
            ns.cleaned_sessions: list[dict[str, Any]] = []
            for ns.item in ns.bps_raw:
                if not isinstance(ns.item, dict):
                    continue
                ns.bid = _safe_int(ns.item.get("body_part_id") or ns.item.get("id"))
                if ns.bid is None or ns.bid <= 0:
                    continue
                ns.sn = _safe_int(ns.item.get("session_number"))
                ns.sess_num = int(ns.sn) if ns.sn is not None and ns.sn >= 1 else 1
                ns.cleaned_sessions.append({"body_part_id": ns.bid, "session_number": ns.sess_num})
            if ns.cleaned_sessions:
                ns.function_args["body_parts_with_sessions"] = ns.cleaned_sessions
                ns.function_args["body_part_ids"] = [ns.x["body_part_id"] for ns.x in ns.cleaned_sessions]
                _remember_booking_selection(ns.user_id, ns.function_args)

        ns.selected_body_part_ids = _normalize_body_part_ids(ns.function_args.get("body_part_ids"))
        if ns.selected_body_part_ids:
            ns.function_args["body_part_ids"] = ns.selected_body_part_ids
            _remember_booking_selection(ns.user_id, ns.function_args)
        elif ns._legacy_inf and ns.selected_service_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
            ns.inferred_bp = await _try_infer_body_part_ids_from_conversation(
                ns.selected_service_id,
                ns.user_input,
                ns.current_context_messages,
                _safe_int(ns.function_args.get("machine_id")),
            )
            if ns.inferred_bp:
                ns.function_args["body_part_ids"] = ns.inferred_bp
                ns.selected_body_part_ids = ns.inferred_bp
                _remember_booking_selection(ns.user_id, ns.function_args)
        if ns.selected_service_id in ns.body_part_required_service_ids and not ns.selected_body_part_ids:
            print("SAFETY: create_appointment missing body_part_ids — handover (no user-text fallback).")
            return {
                "action": "human_handover",
                "handover_degree": "high",
                "bot_reply": "عذراً، ما قدرنا نكمل الحجز آلياً. رح نوصلك لواحد من فريقنا يكمّل معك 🙏"
                if ns.current_preferred_lang in ("ar", "franco")
                else "Sorry, we could not complete booking automatically. A team member will assist you shortly.",
                "detected_language": ns.current_preferred_lang,
                "detected_gender": ns.current_gender,
                "current_gender_from_config": ns.current_gender,
                "escalation_reason": "frustration_detected",
                "_flow_meta": {"error": "create_appointment_missing_body_part_ids"},
            }

        if _safe_int(ns.function_args.get("branch_id")) not in (1, 2):
            ns.api_failure_reason = "invalid_branch_id"
            ns.err_content = json.dumps(
                {
                    "success": False,
                    "message": "branch_id must be 1 (Beirut) or 2 (Antelias) in tool args.",
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

        if not ns.normalize_tool_date(
            ns.function_name,
            ns.function_args,
            user_input_for_date=ns.user_input,
            context_messages_for_date=ns.current_context_messages,
        ):
            ns.err_content = json.dumps(
                {
                    "success": False,
                    "message": "Booking date validation failed; structured date/date_components required from AI.",
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

        # NEW: Remove 'name' from function_args as create_appointment does not accept it directly.
        # This resolves the `unexpected keyword argument 'name'` error.
        if "name" in ns.function_args:
            print(
                f"DEBUG: Removing 'name' argument '{ns.function_args['name']}' from create_appointment call as it's not supported."
            )
            del ns.function_args["name"]
