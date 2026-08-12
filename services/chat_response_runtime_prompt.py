"""get_bot_chat_response prepare (customer file, system prompt, wallet gate)."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    CUSTOMER_STATUS_TOKEN,
    ORCHESTRATION_MODEL,
    Any,
    _build_live_crm_appointments_snapshot,
    _build_multi_appointment_reschedule_hint,
    _clinic_holiday_calendar_block,
    _fetch_customer_file_summary_for_ai,
    _operational_context_promises_imminent_appointment_update,
    _user_message_is_acknowledgment_only,
    config,
    datetime,
    format_clinic_calendar_anchor,
    json,
)


async def prepare_chat_response_prompt(ns: Any) -> Any:

    # Fetch full customer file summary for AI (services, sessions done+available, body parts, payment, dates, machines)
    ns.customer_file_summary = ""
    if ns.customer_phone_clean:
        ns.customer_file_summary_raw = await _fetch_customer_file_summary_for_ai(ns.customer_phone_clean)
        if ns.customer_file_summary_raw:
            ns.customer_file_summary = "\n\n" + ns.customer_file_summary_raw

    ns.domain_scope_policy = (
        "- **Domain Scope Policy**: You only support ليناز ليزر clinic topics (services, pricing, appointments, branches, preparation).\n"
        "- If the user asks out-of-scope general knowledge/news/politics/etc., do NOT answer that question.\n"
        "- Respond with a short polite redirection to clinic-related help.\n"
    )

    # Show greeting only when: new user (no prior messages) OR inactive 12+ hours
    # Prefer Firestore last_ai_response_at (persists across restarts); fallback to in-memory
    ns._now = datetime.datetime.now(datetime.UTC)
    ns._last_bot = (
        ns.last_ai_response_at
        if ns.last_ai_response_at is not None
        else config.user_last_bot_response_time.get(ns.user_id, ns._now)
    )
    if ns._last_bot and getattr(ns._last_bot, "tzinfo", None) is None:
        ns._last_bot = ns._last_bot.replace(tzinfo=datetime.UTC)
    try:
        ns._hours_since = (ns._now - ns._last_bot).total_seconds() / 3600 if ns._last_bot else 0.0
    except (TypeError, AttributeError):
        ns._hours_since = 0.0
    ns._is_new = len(ns.current_context_messages or []) == 0
    ns._show_greeting = ns._is_new or ns._hours_since >= 12
    if ns._show_greeting:
        ns._greeting_reason = "new user (first message)" if ns._is_new else "inactive 12+ hours since last contact"
    else:
        ns._greeting_reason = "ongoing conversation (less than 12 hours since last contact)"

    # Dynamic customer status block - provides current values for the rules defined in style_guide.txt
    ns.dynamic_customer_context = (
        "**📋 CURRENT CUSTOMER STATUS (Use these values when applying the rules from the Style Guide):**\n"
        f"- **customer_exists (CRM file)**: {bool(ns.crm_customer_exists)} — **customer_id**: "
        f"{ns.crm_customer_id if ns.crm_customer_id else '—'}\n"
        "- **Profile lock (server)**: The name, phone, and gender lines below are loaded from the live system each turn. "
        "Do **not** ask the user to repeat them when this block already shows a known name, known gender (male/female), or an existing CRM file.\n"
        f"- **Show greeting**: {ns._show_greeting} - Reason: {ns._greeting_reason}. Use greeting ONLY when True (new user or inactive 12+ hours). Otherwise go straight to the answer. Do NOT repeat أهلاً أستاذ / أنا مروى in every message.\n"
        f"- **Customer Name**: {ns.customer_name_context}\n"
        f"- **Customer Phone**: '{ns.customer_phone_clean}' - Use this for ALL tool calls (check_next_appointment, submit_booking_intent, create_appointment if ever used, update_appointment_date). Do NOT ask for phone number.\n"
        f"- **Gender**: '{ns.current_gender}'"
        + (
            " - GENDER IS ALREADY KNOWN. NEVER ask for gender again!\n"
            if ns.current_gender in ["male", "female"]
            else " - UNKNOWN. Follow gender collection rules in Style Guide.\n"
        )
        + "- **Profile correction rule**: If the user explicitly asks to change/correct their saved name or gender, call `update_customer_profile` with the new value before replying. Do not only set detected_name/detected_gender.\n"
        + f"- **Language**: YOU decide. Current hint: '{ns.current_preferred_lang}'. Follow LANGUAGE rules: prefer Arabic when mixed; full English when all English; full French when all French.\n"
        + ns.arabic_script_policy
        + ns.arabic_addressing_policy
        + ns.arabic_brand_policy
        + ns.arabic_date_policy
        + ns.concise_turn_policy
        + ns.domain_scope_policy
        + f"- **current_gender_from_config**: '{ns.current_gender}'\n"
        f"- **detected_language**: '{ns.current_preferred_lang}'\n"
        f"- **Awaiting human handover confirmation**: {config.user_data_whatsapp.get(ns.user_id, {}).get('awaiting_human_handover_confirmation', False)} - If True, user is replying to your transfer confirmation question. Interpret yes/no accordingly.\n"
        f"**🕐 CURRENT DATE AND TIME (UTC+0200): {ns.current_day_name}, {ns.current_date_str} at {ns.current_time_str}**\n"
        f"**📅 CALENDAR ANCHOR (do not guess today/tomorrow; use this):** {format_clinic_calendar_anchor(ns.current_local_time)}\n"
        f"{_clinic_holiday_calendar_block(ns.user_id, ns.current_local_time)}"
        f"{ns.customer_file_summary}" + ((f"\n\n{ns.booking_fsm_prompt_block}") if ns.booking_fsm_prompt_block else "")
    )
    if ns.social_channel:
        ns.dynamic_customer_context += (
            "\n\n**SOCIAL CHANNEL POLICY (MANDATORY):**\n"
            "- This conversation is on Instagram/Facebook, not WhatsApp.\n"
            "- Never create, change, cancel, confirm, list, or check an appointment or customer CRM record here.\n"
            "- Never claim an appointment is booked or submitted.\n"
            "- Appointment and human-agent requests are handled by a deterministic server router that asks for branch/gender and provides a WhatsApp-only contact.\n"
            "- You may answer general questions about services, prices, branches, preparation, and policies normally.\n"
        )

    # Compact customer context for Activity Flow visibility (what Bot sends to AI about this customer)
    ns._file_raw = ns.customer_file_summary.strip().lstrip("\n") if ns.customer_file_summary else ""
    ns.flow_customer_context_sent = (
        "=== CUSTOMER STATUS ===\n"
        f"- customer_exists: {bool(ns.crm_customer_exists)}\n"
        f"- customer_id: {ns.crm_customer_id or '(none)'}\n"
        f"- Name: {ns.customer_name_context}\n"
        f"- Phone: {ns.customer_phone_clean or '(none)'}\n"
        f"- Gender: {ns.current_gender}\n"
        f"- Language hint: {ns.current_preferred_lang}\n\n"
        "=== CUSTOMER FILE (services, sessions, body parts, payment, dates – done+available only) ===\n"
        + (ns._file_raw if ns._file_raw else "(No file or customer not found)")
    )

    ns.reschedule_multi_hint = ""
    if ns.is_reschedule_intent and ns.customer_phone_clean:
        ns.reschedule_multi_hint = await _build_multi_appointment_reschedule_hint(ns.customer_phone_clean)

    ns.routing_guardrail = ""
    if ns.is_reschedule_intent:
        ns.routing_guardrail = (
            "\n\n"
            "**🔒 INTENT ROUTING OVERRIDE:**\n"
            "- The user's latest request is to RESCHEDULE/POSTPONE an appointment.\n"
            "- This is NOT a clinic working-hours request.\n"
            "- Do NOT call `get_clinic_hours` for this message.\n"
            "- Use appointment flow only: `check_next_appointment` then `update_appointment_date` when date/time is provided.\n"
        )
        if ns.reschedule_multi_hint:
            ns.routing_guardrail += ns.reschedule_multi_hint

    if ns.is_existing_appointment_edit_intent:
        ns.routing_guardrail += (
            "\n\n"
            "**🛠️ EXISTING APPOINTMENT EDIT (THIS MESSAGE):**\n"
            "- The user wants to modify an already booked appointment (for example: change machine/device, add/remove body areas, switch service, or change branch).\n"
            "- This is **NOT** a new booking flow. Do **NOT** ask full booking questions again if the appointment row already exists in CRM.\n"
            "- Do **NOT** use `submit_booking_intent` or `create_appointment` for this request.\n"
            "- First identify the correct existing row with `check_next_appointment`; if several rows exist, ask for `appointment_id` or the line number only.\n"
            "- If the chosen row is **PAUSED / موقوف** and the user is editing it to continue/resume treatment, you MUST make it **Available** in the **same execution turn**. Do **not** leave it paused after the edit.\n"
            "- **Date-only paused change:** use **`update_appointment_date`** on that paused row.\n"
            "- **Paused row + machine/body-part/date details:** prefer **`update_paused_appointment`** and explicitly set **`status` = `Available`**.\n"
            "- **Paused row + service/branch or any edit that still needs `edit_appointment`:** call **`edit_appointment`** for the detail change **and** call **`resume_appointment`** in the same turn for that same `appointment_id`.\n"
            "- **Non-paused existing rows:** use **`edit_appointment`** for machine/body-part/service/branch edits. Use **`update_appointment_date`** only when the change is date/time only.\n"
            "- Reuse the current appointment facts from CRM and ask only for the single missing detail needed to complete the edit.\n"
        )

    if ns.is_appointment_inquiry_intent and ns.customer_phone_clean:
        ns.routing_guardrail += (
            "\n\n"
            "**📅 APPOINTMENT STATUS / LISTING (THIS MESSAGE — MANDATORY):**\n"
            "- The user is asking **when** their appointment is, **what** is on file, or to **list** bookings (including paused / موقوف) — e.g. Franco «emtan mw3de», Arabic «موعدي إمتى», English «when is my appointment», «sho hene el mw3id el wa2fe», etc.\n"
            "- A **LIVE CRM APPOINTMENT SNAPSHOT** block is appended below this prompt with the current rows — **ground your list on it** (correct row count and ids). You **MUST** still call **`check_next_appointment`** this turn with the customer phone from context.\n"
            "- The tool response is enriched with **`customer_appointments`**: list **every** row returned. **One line per row**, each with **`appointment_id`**, date & time, service, branch, machine if present, body areas if present, price/total **only if JSON has it**.\n"
            "- **Never merge** several paused or active rows into one vague line (e.g. do not collapse multiple men's hair rows into «مرتين بنفس الوقت» unless the API literally returns a single row). If there are 5 paused lines, show **5** lines.\n"
            "- Clearly separate **active/upcoming** vs **paused** using the **status** field from JSON — do not guess.\n"
            "- If they need to **choose one** row to change: ask for **`appointment_id`** (رقم الموعد) or the line number matching your list.\n"
        )

    if ns.is_bulk_reschedule_all_intent and ns.customer_phone_clean:
        ns.routing_guardrail += (
            "\n\n"
            "**🔁 BULK RESCHEDULE — ALL LISTED ROWS (THIS MESSAGE):**\n"
            "- The user asked to move **every** relevant appointment (often all paused lines) to the **same** new date/time (e.g. Franco «3mlon kelon», «kelon bokra», Arabic «كلهم»).\n"
            "- You MUST call **`update_appointment_date` once per distinct `appointment_id`** from the **LIVE CRM APPOINTMENT SNAPSHOT** (several tool calls in **this** turn).\n"
            "- **Forbidden:** Saying «تم تعديل كل المواعيد» / «صاروا كلهم» / «كلهم ببكرا» unless **each** of those tool calls returned **success** in this request.\n"
            "- If you only updated one row, say so honestly and offer to continue with the remaining ids — never claim all seven (or «الكل») are done.\n"
        )

    # Enforce explicit json contract whenever response_format={"type":"json_object"} is used.
    # Some OpenAI endpoints reject requests if the messages omit the word "json".
    ns.json_output_contract = (
        "\n\nOUTPUT FORMAT (MANDATORY):\n"
        "- Reply with a valid json object only.\n"
        '- Include at least these keys: "action" and "bot_reply".\n'
        '- : "booking_fsm_patch" — object with any of: service_id, branch_id, machine_id, body_part_ids, '
        "appointment_date (YYYY-MM-DD), appointment_time (HH:MM), confirmed_booking (true only after explicit user yes to final summary).\n"
        "- Do not return markdown, code fences, or extra text outside json.\n"
    )

    # Combine system instruction with dynamic context (replace token or append)
    if CUSTOMER_STATUS_TOKEN in ns.system_instruction_core:
        ns.system_instruction_final = (
            ns.system_instruction_core.replace(CUSTOMER_STATUS_TOKEN, "\n\n" + ns.dynamic_customer_context)
            + ns.routing_guardrail
            + ns.json_output_contract
        )
    else:
        ns.system_instruction_final = (
            ns.system_instruction_core + "\n\n" + ns.dynamic_customer_context + ns.routing_guardrail + ns.json_output_contract
        )

    # Steer the model when the user only confirms after we promised an appointment update (Ok/deal/تمام…).
    if not ns.user_image_base64 and _user_message_is_acknowledgment_only(ns.user_input):
        ns._pend_update = _operational_context_promises_imminent_appointment_update(ns.operational_context)
        if not ns._pend_update:
            for ns._msg in reversed(ns.current_context_messages or []):
                if ns._msg.get("role") == "assistant":
                    ns._pend_update = _operational_context_promises_imminent_appointment_update(
                        str(ns._msg.get("content") or "")
                    )
                    break
        if ns._pend_update:
            ns.system_instruction_final += (
                "\n\n**⚡ PENDING-OPERATION CONFIRMATION (THIS TURN ONLY):**\n"
                "- The user's latest message is only a short **yes / ok / proceed** style confirmation.\n"
                "- Your previous assistant turn (or thread context) already committed to **updating or rescheduling** an appointment.\n"
                "- **Interpret** their reply as authorization to **execute that same operation now**.\n"
                "- You MUST call the real tools in this response: `check_next_appointment` if you still need `appointment_id`, then use **`update_appointment_date`** for date/time-only changes or **`edit_appointment`** / **`update_paused_appointment`** for detail changes already agreed in the conversation.\n"
                "- If that row is **PAUSED** and this confirmation means they want to continue, you MUST also ensure the same execution turn removes pause and returns it to **Available** (either **`update_paused_appointment status=Available`** or **`resume_appointment`** when needed).\n"
                "- Do **not** claim the update is done in `bot_reply` unless the real update tool actually succeeded in this request.\n"
            )

    # Authoritative CRM rows in-system so «emtan mw3de» / multi-paused listings cannot be hallucinated or merged.
    if (
        ns.is_appointment_inquiry_intent or ns.is_reschedule_intent or ns.is_existing_appointment_edit_intent
    ) and ns.customer_phone_clean:
        ns._live_snap = await _build_live_crm_appointments_snapshot(ns.customer_phone_clean)
        if ns._live_snap:
            ns.system_instruction_final += ns._live_snap

    ns.context_messages_for_ai = []
    for ns._ctx_msg in ns.current_context_messages or []:
        if not isinstance(ns._ctx_msg, dict):
            continue
        ns._role = str(ns._ctx_msg.get("role") or "user").strip().lower()
        if ns._role not in ("system", "assistant", "user", "function", "tool"):
            ns._role = "assistant"
        ns._content = ns._ctx_msg.get("content", ns._ctx_msg.get("text", ""))
        if ns._content is None:
            ns._content = ""
        elif not isinstance(ns._content, str):
            ns._content = json.dumps(ns._content, ensure_ascii=False, default=str)
        ns.context_messages_for_ai.append({"role": ns._role, "content": ns._content})
    ns.context_cap = int(getattr(config, "MAX_CONTEXT_MESSAGES_IN_WINDOW", 0) or 0)
    if ns.context_cap > 0 and len(ns.context_messages_for_ai) > ns.context_cap:
        ns.context_messages_for_ai = ns.context_messages_for_ai[-ns.context_cap:]

    if len(ns.context_messages_for_ai) < 4:
        ns.system_instruction_final += (
            "\n\n**THREAD LENGTH NOTE:** CONTEXT MESSAGES below may be short (e.g. testing without full Firestore history). "
            "Use CUSTOMER STATUS and any «Last message we sent to the user» line from operational context. "
            "Short replies such as «eh» / «إيه» / «نعم» usually confirm the last bot question—continue booking/pricing, do not reset to a generic greeting.\n"
        )

    ns.messages = [{"role": "system", "content": ns.system_instruction_final}]
    ns.messages.extend(ns.context_messages_for_ai)

    # Build user message: text only, or multimodal (text + image) when image provided
    if ns.user_image_base64:
        ns.image_url = f"data:image/{ns.user_image_format};base64,{ns.user_image_base64}"
        ns.user_content = [
            {"type": "text", "text": ns.user_input or "المستخدم أرسل صورة."},
            {"type": "image_url", "image_url": {"url": ns.image_url}},
        ]
        ns.messages.append({"role": "user", "content": ns.user_content})
    else:
        ns.messages.append({"role": "user", "content": ns.user_input})

    # Prepare flow metadata context early so Activity Flow remains informative
    # even when GPT fails before normal metadata assembly.
    ns.flow_context_count = len(ns.context_messages_for_ai)
    ns.flow_sys_len = len(ns.system_instruction_final) if ns.system_instruction_final else 0
    ns.flow_ai_query_summary = (
        f"Bot sent to AI (GPT):\n"
        f"- System prompt: {ns.flow_sys_len} chars (knowledge + style + customer context)\n"
        f"- Context messages: {ns.flow_context_count}\n"
        f"- User query: {ns.user_input[:400]}{'...' if len(ns.user_input) > 400 else ''}"
    )
    if ns.custom_knowledge_context:
        ns.flow_ai_query_summary += (
            f"\n- Dynamic knowledge: {len(ns.custom_knowledge_context)} chars, full content:\n{ns.custom_knowledge_context}"
        )
    ns.flow_context_dump = []
    for ns.msg in ns.context_messages_for_ai:
        ns.role = ns.msg.get("role", "unknown")
        ns.content = str(ns.msg.get("content", ""))
        ns.flow_context_dump.append(f"[{ns.role}] {ns.content}")
    ns.flow_bot_sent_to_ai_full = (
        "Bot sent to AI (GPT) - FULL INPUT\n\n"
        "=== SYSTEM PROMPT ===\n"
        f"{ns.system_instruction_final}\n\n"
        "=== CONTEXT MESSAGES ===\n"
        + ("\n".join(ns.flow_context_dump) if ns.flow_context_dump else "(none)")
        + "\n\n=== USER MESSAGE ===\n"
        + str(ns.user_input)
    )

    ns.gpt_raw_content = ""  # Initialize gpt_raw_content here to make it accessible in except blocks

    # Stage split: keep orchestration/tool-routing on 5.1; final user-facing response after tools on 5.4-mini.
    ns.selected_model = ORCHESTRATION_MODEL
    ns.model_metadata = {
        "complexity": "FIXED",
        "reason": f"Planning/tool-routing on {ORCHESTRATION_MODEL}",
    }
    print(f"🤖 Model selected: {ns.selected_model} | Reason: {ns.model_metadata['reason']}")

    # Prepaid wallet gate (FAQ/static paths never reach here). Unlimited tenants bypass.
    try:
        from services.token_metering import RECHARGE_REQUIRED_MESSAGE, assert_tenant_can_use_ai
        from services.token_wallet_service import InsufficientTokenBalance

        ns._ud = config.user_data_whatsapp.get(ns.user_id) or {}
        ns._tenant = str(ns._ud.get("tenant_id") or ns._ud.get("tenantId") or "").strip()
        if not ns._tenant:
            return {
                "action": "reply",
                "reply": "Unable to process this request because the workspace could not be identified. Please try again later.",
                "source": "tenant_required",
                "_flow_meta": {
                    "source": "tenant_required",
                    "ai_called": False,
                    "cost_status": "none",
                    "tokens": 0,
                },
            }
        assert_tenant_can_use_ai(ns._tenant)
    except InsufficientTokenBalance:
        return {
            "action": "reply",
            "reply": RECHARGE_REQUIRED_MESSAGE,
            "source": "token_wallet_empty",
            "_flow_meta": {
                "source": "token_wallet_empty",
                "ai_called": False,
                "cost_status": "none",
                "tokens": 0,
            },
        }
