"""get_bot_chat_response prepare (identity, rate limits, prompt policies)."""

from __future__ import annotations

from services.chat_response_runtime_common import (
    Any,
    _contains_arabic_script,
    _get_body_part_required_service_ids,
    check_rate_limits,
    config,
    detect_appointment_inquiry_intent,
    detect_bulk_reschedule_all_intent,
    detect_existing_appointment_edit_intent,
    detect_reschedule_intent,
    get_gender_from_gpt,
    get_rate_limit_response,
    get_system_instruction,
    is_price_related_question,
    json,
    now_in_bot_tz,
)


async def prepare_chat_response_identity(ns: Any) -> Any:
    ns.user_name = config.user_names.get(ns.user_id, "client")
    ns.social_channel = str(config.user_data_whatsapp.get(ns.user_id, {}).get("channel") or "").strip().lower() in {
        "instagram",
        "facebook",
    }

    # Extract customer phone number (without country code for API calls)
    ns.customer_phone_full = None if ns.social_channel else config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")

    # CRITICAL: Sync CRM lookup when we have phone but no known name (fixes race: defer_external
    # runs in background, so AI was called before CRM name arrived - bot asked for name when customer has file)
    ns._placeholder_names = {
        "client",
        "unknown",
        "unknown customer",
        "instagram customer",
        "facebook customer",
        "customer",
        "test user",
    }
    ns._name_lower = (ns.user_name or "").strip().lower()
    ns._name_unknown = (
        not ns.user_name
        or ns.user_name == "client"
        or ns._name_lower in ns._placeholder_names
        or ns._name_lower.startswith("test user")
    )
    if ns.customer_phone_full and ns._name_unknown:
        from utils.phone_utils import normalize_phone

        ns.normalized_for_crm = normalize_phone(ns.customer_phone_full) or (
            str(ns.customer_phone_full).strip() if str(ns.customer_phone_full).strip().startswith("+") else ""
        )
        if ns.normalized_for_crm:
            try:
                from services.customer_identity_service import resolve_customer_from_external

                ns.ext = await resolve_customer_from_external(ns.normalized_for_crm)
                if ns.ext.get("exists") and ns.ext.get("name"):
                    config.user_names[ns.user_id] = ns.ext["name"]
                    ns.user_name = ns.ext["name"]
                    if ns.user_id in config.user_data_whatsapp:
                        config.user_data_whatsapp[ns.user_id]["crm_customer_exists"] = True
                        config.user_data_whatsapp[ns.user_id]["customer_file_status"] = "existing_file"
                        if ns.ext.get("external_id"):
                            config.user_data_whatsapp[ns.user_id]["crm_customer_id"] = ns.ext["external_id"]
                    # Also set gender from customer file so we don't ask when it's already in CRM
                    if ns.ext.get("gender") in ("male", "female"):
                        config.user_gender[ns.user_id] = ns.ext["gender"]
                        config.gender_attempts[ns.user_id] = 0
                        print(
                            f"✅ CRM sync: loaded name '{ns.user_name}' and gender '{ns.ext['gender']}' for {ns.user_id} before AI call"
                        )
                    else:
                        print(f"✅ CRM sync: loaded name_len={len(str(ns.user_name or ''))} for ...{str(ns.user_id)[-4:]} before AI call")
                elif ns.ext.get("exists"):
                    if ns.user_id in config.user_data_whatsapp:
                        config.user_data_whatsapp[ns.user_id]["crm_customer_exists"] = True
                        config.user_data_whatsapp[ns.user_id]["customer_file_status"] = "existing_file"
                        if ns.ext.get("external_id"):
                            config.user_data_whatsapp[ns.user_id]["crm_customer_id"] = ns.ext["external_id"]
                    # Customer has file but no name - still try to use gender if present
                    if ns.ext.get("gender") in ("male", "female"):
                        config.user_gender[ns.user_id] = ns.ext["gender"]
                        config.gender_attempts[ns.user_id] = 0
                        print(f"✅ CRM sync: customer has file, loaded gender '{ns.ext['gender']}' for ...{str(ns.user_id)[-4:]}")
                    else:
                        print(f"✅ CRM sync: customer has file but no name in CRM for ...{str(ns.user_id)[-4:]}")
            except Exception as e:
                print(f"⚠️ CRM sync lookup failed for ...{str(ns.user_id)[-4:]}: {e}")
        # Use gender from config if we just loaded it from CRM (for current request)
        if config.user_gender.get(ns.user_id) in ("male", "female"):
            ns.current_gender = config.user_gender[ns.user_id]
    ns.customer_phone_clean = None
    if ns.customer_phone_full:
        ns.customer_phone_clean = str(ns.customer_phone_full).replace("+", "").replace(" ", "").replace("-", "")
        if ns.customer_phone_clean.startswith("961"):
            ns.customer_phone_clean = ns.customer_phone_clean[3:]  # Remove Lebanon country code

    # Authoritative server profile (after CRM sync) — booking FSM + prompts must not re-ask these
    ns.user_name = config.user_names.get(ns.user_id, "client")
    ns._placeholder_names_profile = {
        "client",
        "unknown",
        "unknown customer",
        "instagram customer",
        "facebook customer",
        "customer",
        "test user",
    }
    ns._name_lower_profile = (ns.user_name or "").strip().lower()
    ns.name_is_known = (
        ns.user_name
        and ns.user_name != "client"
        and ns._name_lower_profile not in ns._placeholder_names_profile
        and not ns._name_lower_profile.startswith("test user")
    )
    ns.crm_customer_exists = config.user_data_whatsapp.get(ns.user_id, {}).get("crm_customer_exists")
    ns.crm_customer_id = config.user_data_whatsapp.get(ns.user_id, {}).get("crm_customer_id")

    # Check rate limits first
    ns.within_limits, ns.limit_message = await check_rate_limits(ns.user_id, "message")
    if not ns.within_limits:
        return {
            "action": "rate_limit_exceeded",
            "bot_reply": get_rate_limit_response(ns.current_preferred_lang, ns.limit_message),
            "detected_language": ns.current_preferred_lang,
            "current_gender_from_config": ns.current_gender,
        }

    ns.explicitly_detected_gender_from_input = None
    if ns.user_input.strip():
        ns.explicitly_detected_gender_from_input = await get_gender_from_gpt(ns.user_input)
        print(
            f"DEBUG GPT Gender Recognition: Input '{ns.user_input}' -> Detected as '{ns.explicitly_detected_gender_from_input}' (for logging/debug, GPT will decide action)"
        )

    ns.is_reschedule_intent = detect_reschedule_intent(ns.user_input)
    ns.is_appointment_inquiry_intent = detect_appointment_inquiry_intent(ns.user_input)
    ns.is_bulk_reschedule_all_intent = detect_bulk_reschedule_all_intent(ns.user_input)
    ns.is_existing_appointment_edit_intent = detect_existing_appointment_edit_intent(ns.user_input)
    if ns.is_reschedule_intent:
        print("🔁 Intent routing lock: reschedule/postpone intent detected.")
    if ns.is_appointment_inquiry_intent:
        print("📅 Intent routing: appointment status / listing inquiry detected.")
    if ns.is_bulk_reschedule_all_intent:
        print("🔁 Intent routing: bulk reschedule ALL rows requested.")
    if ns.is_existing_appointment_edit_intent:
        print("🛠️ Intent routing: existing appointment edit detected.")

    ns.booking_fsm_prompt_block = ""
    try:
        from services.booking import booking_fsm as _booking_fsm_mod

        if _booking_fsm_mod.fsm_enabled() and not ns.social_channel:
            if not (
                ns.is_reschedule_intent
                or ns.is_appointment_inquiry_intent
                or ns.is_bulk_reschedule_all_intent
                or ns.is_existing_appointment_edit_intent
            ):
                _booking_fsm_mod.maybe_enter_booking_mode(ns.user_id, ns.user_input)
            _booking_fsm_mod.maybe_exit_booking_mode(ns.user_id, ns.user_input)
            _booking_fsm_mod.sync_from_flat_booking_state(ns.user_id)
            _booking_fsm_mod.set_session_context(
                ns.user_id,
                ns.current_gender,
                ns.customer_phone_clean or "",
                customer_display_name=(ns.user_name if ns.name_is_known else None),
                crm_customer_file=bool(ns.crm_customer_exists),
                customer_id=str(ns.crm_customer_id).strip() if ns.crm_customer_id else None,
            )
            if ns.explicitly_detected_gender_from_input in ("male", "female"):
                _booking_fsm_mod.lock_gender_from_user_message(ns.user_id, ns.explicitly_detected_gender_from_input)
            _booking_fsm_mod.infer_body_area_from_user_message(ns.user_id, ns.user_input)
            _booking_fsm_mod.apply_heuristic_confirmation(ns.user_id, ns.user_input)
            ns.booking_fsm_prompt_block = _booking_fsm_mod.build_prompt_block(ns.user_id, ns.current_gender)
            if ns.booking_fsm_prompt_block:
                ns._fsm_snap = config.user_booking_state[ns.user_id].get("booking_fsm") or {}
                ns._g_fs = ns._fsm_snap.get("customer_gender") or ns.current_gender
                ns._ok_fc, ns._miss_fc = _booking_fsm_mod.fields_complete(ns._fsm_snap, ns._g_fs)
                ns._nxt_fc = _booking_fsm_mod.first_missing_field_for_user_chat(ns._fsm_snap, ns._g_fs, ns.user_id)
                ns._can_ex, ns._gr = _booking_fsm_mod.can_execute_submit(ns.user_id, ns.current_gender)
                _booking_fsm_mod.record_decision_log(
                    ns.user_id,
                    phase="pre_gpt",
                    next_field=ns._nxt_fc,
                    gate=ns._gr or ("ready" if ns._can_ex else "blocked"),
                    extracted={"user_message_excerpt": (ns.user_input or "")[:240]},
                )
                try:
                    ns._u_act = _booking_fsm_mod.build_unified_booking_snapshot(
                        ns.user_id,
                        ns.current_gender,
                        customer_exists=bool(ns.crm_customer_exists),
                        customer_id=str(ns.crm_customer_id).strip() if ns.crm_customer_id else None,
                        name_is_known=bool(ns.name_is_known),
                        crm_data_used=bool(ns._fsm_snap.get("crm_profile_applied")),
                    )
                    print("[BOOKING_ACTIVITY] " + json.dumps(ns._u_act, ensure_ascii=False, default=str)[:12000])
                except Exception as _ba_e:
                    print(f"⚠️ BOOKING_ACTIVITY log: {_ba_e}")
    except Exception as _fsm_init_e:
        print(f"⚠️ booking_fsm pre-gpt: {_fsm_init_e}")

    # NOTE: conversation_log.jsonl is NO LONGER USED
    # Q&A matching is now handled by qa_database_service.py (API-based)
    # This happens in text_handlers.py BEFORE calling this function
    # If we reach here, it means no Q&A match was found, so proceed with GPT-4

    # Trained Q&A partial-match injection into the system prompt is intentionally disabled.
    # Exact Q&A matching still happens earlier in text_handlers.py before this GPT path.
    ns.qa_reference_text = ""

    # Detect if this is a price-related question and load sync rules.
    # Use booking state too, so weak words like "kam" do not misfire out of context.
    ns.booking_state_snapshot = config.user_booking_state.get(ns.user_id, {})
    ns.is_price_question = is_price_related_question(ns.user_input, ns.booking_state_snapshot)
    ns.body_part_required_service_ids = _get_body_part_required_service_ids()

    # Get the core system instruction from utils.py, with conditional price list loading.
    # When custom_knowledge_context is provided (from dynamic retrieval), ADDITIVE to KB/Style.
    # Legacy path only reaches here for the temporary linas bridge (Wave 6 removes it).
    # Per-tenant published CM answers never enter this function.
    ns._published = False
    ns.system_instruction_core = get_system_instruction(
        ns.user_id,
        ns.current_preferred_lang,
        ns.qa_reference_text,
        include_price_list=(ns.is_price_question and not ns._published),
        custom_knowledge_context=(None if ns._published else ns.custom_knowledge_context),
        operational_context=ns.operational_context,
    )

    # Log which training files GPT is receiving (legacy path only)
    if ns._published:
        print("📄 CM published mode: skipping knowledge_base.txt / style_guide.txt / price_list.txt injection")
    else:
        print("📄 GPT will receive knowledge_base.txt in context")
        print("📄 GPT will receive style_guide.txt in context")

        if ns.is_price_question:
            print("📄 GPT will receive price_list.txt in context (price-related question detected)")
        else:
            print("📄 GPT will skip price_list.txt in context (not a price-related question)")

    # Build dynamic customer context - just the VALUES, rules are in style_guide.txt
    # user_name, name_is_known, crm_customer_exists: set after CRM sync (see block above)
    ns.customer_first_name = (
        (ns.user_name.split()[0] if ns.user_name and ns.user_name != "client" else ns.user_name) if ns.user_name else None
    )
    ns._placeholder_names = {
        "client",
        "unknown",
        "unknown customer",
        "instagram customer",
        "facebook customer",
        "customer",
        "test user",
    }
    ns._name_lower = (ns.user_name or "").strip().lower()
    ns.current_local_time = now_in_bot_tz()
    ns.current_date_str = ns.current_local_time.strftime("%Y-%m-%d")
    ns.current_time_str = ns.current_local_time.strftime("%H:%M:%S")
    ns.current_day_name = ns.current_local_time.strftime("%A")

    ns.arabic_script_policy = ""
    if ns.response_language in ("ar", "franco"):
        ns.arabic_script_policy = (
            "- **Arabic Script Only (NO MIXING)**: Your `bot_reply` MUST be in Arabic script only (no Latin letters at all). "
            "NEVER mix English with Arabic. BANNED in Arabic messages: 'AI Assistant', 'Marwa', 'Lina's Laser', or ANY Latin/English words. "
            "Write clinic as ليناز ليزر, assistant as مروى only. When introducing yourself: أهلاً، أنا مروى من ليناز ليزر – never 'مروى AI Assistant'.\n"
        )

    ns.customer_name_context = "NOT KNOWN - You MUST ask for their full name (see Name Capture Rules in Style Guide)"
    if ns.name_is_known:
        ns.customer_name_context = f"KNOWN - {ns.user_name} (First name: {ns.customer_first_name}). Do NOT ask for name again."
    elif ns.crm_customer_exists:
        ns.customer_name_context = (
            "Customer has EXISTING FILE in CRM - do NOT ask for their name. "
            "Use respectful address (حضرتك/أستاذ/عزيزتي) without requesting name. "
            "Proceed to help with their inquiry."
        )

    ns.arabic_addressing_policy = ""
    if ns.response_language in ("ar", "franco"):
        if ns.name_is_known and not _contains_arabic_script(ns.user_name):
            ns.customer_name_context = (
                f"KNOWN (non-Arabic script name): {ns.user_name}. "
                "In Arabic replies, transliterate this name to Arabic letters and include it after the respectful title."
            )

        ns.arabic_addressing_policy = (
            "- **Arabic Addressing Rule**: Use respectful addressing in Arabic replies only:\n"
            "  - male: أستاذ\n"
            "  - female: عزيزتي\n"
            "  - unknown gender: حضرتك\n"
            "  If customer name is known, include it after the respectful title in Arabic letters.\n"
            "  Never use 'يا' followed by a transliterated name (example: يا تست).\n"
        )

    ns.arabic_brand_policy = ""
    ns.arabic_date_policy = ""
    if ns.response_language in ("ar", "franco"):
        ns.arabic_brand_policy = (
            "- **Arabic Clinic Naming Rule**: When mentioning the clinic, write exactly: ليناز ليزر (never Lina's Laser in Latin).\n"
            "- **Assistant Intro in Arabic**: Say أهلاً، أنا مروى من ليناز ليزر. NEVER write 'AI Assistant' or 'Marwa AI Assistant' – zero Latin script in Arabic messages.\n"
        )
        ns.arabic_date_policy = (
            "- **Arabic Date/Time Rule (MANDATORY)**: When your bot_reply is in Arabic, ALL dates and times MUST be in Arabic format. "
            "Use Arabic numerals (٠١٢٣٤٥٦٧٨٩) and Arabic month names. Example: 01/04/2026 10:00 → ١ نيسان ٢٠٢٦ الساعة ١٠:٠٠ صباحاً. "
            "Months: يناير، فبراير، مارس، أبريل/نيسان، مايو، يونيو، يوليو، أغسطس، سبتمبر، أكتوبر، نوفمبر، ديسمبر (or Levantine: كانون الثاني، شباط، آذار، نيسان، أيار، حزيران، تموز، آب، أيلول، تشرين الأول، تشرين الثاني، كانون الأول). "
            "NEVER use 01/04/2026 or DD/MM/YYYY in Arabic messages – always convert to Arabic.\n"
        )

    ns.concise_turn_policy = (
        "- **Turn-by-Turn Policy (CRITICAL)**: ONE message only. Short and focused.\n"
        "- **Response Length (MANDATORY)**: Keep bot_reply concise. Aim for ~30% shorter than a full detailed answer. "
        "Neither too long (avoid 3+ paragraphs, long numbered lists, repeated points) nor too short (keep essential info). "
        "One focused paragraph or 2–3 brief bullet points max. Cut filler and repetition.\n"
        "- Either: (a) short answer + ONE question, OR (b) ONE question to gather info.\n"
        "- **Exception — multiple CRM appointments:** If you must list several rows for the user to choose (reschedule / resume pause), use **one compact line per row** "
        "(appointment_id + date/time + service + branch + machine + areas + price only if in JSON), then **one** question asking for **`appointment_id`** or line number.\n"
        "- **Do NOT** ask for booking details (body part, machine, service, size, branch, date, time, name) unless the user is "
        "**booking** or **needs a price that depends on missing data**. On general questions, answer directly without pushing extra questions.\n"
        "- When booking/pricing needs more data: ask **only missing** fields (body part, machine only for hair removal, service, size for tattoo, branch, date, time). Never re-ask known facts.\n"
        "- After confirming a slot or total price: state clearly **when**, **what service/area**, and **cost** if relevant.\n"
        "- Do NOT dump service info + availability + pricing + multiple questions in one message unless the user explicitly asked for that depth.\n"
    )
