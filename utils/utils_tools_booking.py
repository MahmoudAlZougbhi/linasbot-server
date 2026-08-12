"""OpenAI tool schema: profile + booking mutations."""

from __future__ import annotations

from typing import Any

OPENAI_BOOKING_TOOLS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "update_customer_profile",
                "description": (
                    "Update the saved profile for the current WhatsApp user when they explicitly ask to correct/change "
                    "their name or gender, or they say the bot is addressing them with the wrong gender/name. "
                    "Use this before replying to confirmations like 'my name is X now', 'change my name to X', "
                    "'I am female not male', 'ana bent mesh shab', or Arabic/franco equivalents. "
                    "Do not call this for weak inference; only when the user clearly provides the new value."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "new_name": {
                            "type": "string",
                            "description": "The corrected customer display name exactly as the user wants it saved. Omit if not changing name.",
                        },
                        "new_gender": {
                            "type": "string",
                            "enum": ["male", "female"],
                            "description": "Corrected gender in normalized backend format. Omit if not changing gender.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Short reason from the user's message, e.g. 'user requested gender correction'.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_booking_intent",
                "description": (
                    "DEFAULT and REQUIRED path for every NEW booking: send structured extraction from the conversation. "
                    "The bot validates every field, resolves names to IDs using live CRM lists, enforces clinic slot rules, "
                    "then calls the CRM create endpoint only if validation passes. "
                    "Do NOT tell the user the appointment is booked unless this tool returns success with booking_flow_state=booked. "
                    "Do NOT use create_appointment for normal new bookings—use this tool first. "
                    "Leave IDs null when unsure; use get_services/get_branches/get_machines/get_body_parts first if needed. "
                    "Only Laser Hair Removal Men/Women (service_id 1/12) require a machine. For every other service, do NOT ask for machine and do NOT send machine_id. "
                    "If the user already supplied service, area, branch, date, time, and machine when required for hair removal in one message, extract all of them into this tool call; do not ask the same fields again. "
                    "DATETIME: Before execute_booking=true, resolve all relative NL into absolute values (Asia/Beirut). "
                    "IDs: By default the server does NOT convert service_name/branch_name/machine_name/body text to ids — "
                    "you MUST call get_services, get_branches, get_machines, get_body_parts and send service_id, branch_id, "
                    "machine_id (when required), body_part_ids, plus date/time/timezone. "
                    "Do not send name-only payloads with execute_booking=true. "
                    "raw_user_* and calendar_day_intent are optional trace fields only. "
                    "Legacy name resolution on the server exists only if the deployment sets LINASLASER_BOOKING_BACKEND_RESOLVES_NAMES=true. "
                    "For reschedule use update_appointment_date, not this tool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "enum": ["create_appointment"],
                            "description": "Must be create_appointment for a new booking.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Customer phone without country code when possible; omit if same as runtime context.",
                        },
                        "service_name": {"type": "string", "description": "Human-readable service from user."},
                        "service_id": {"type": "integer", "description": "Only if already verified from get_services."},
                        "body_part": {
                            "type": "string",
                            "description": "Human-readable area hint from the user. Preserve it even when body_part_ids are available; never ask again when user already gave it.",
                        },
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Non-empty list of CRM ids: call get_body_parts(service_id=…) and map every user-mentioned area to ids (multiple areas = multiple ids).",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "session_number": {
                                        "type": "integer",
                                        "description": "Per-area session index (1=first visit for that area, 2+=follow-up). Omit entirely for normal first bookings; server defaults all to 1.",
                                    },
                                },
                            },
                            "description": ". When session numbers differ per area, pass one row per id (same ids as body_part_ids). Server sends BOC body_parts as {id, session_number} per official API doc.",
                        },
                        "machine_name": {
                            "type": "string",
                            "description": "Device name for Laser Hair Removal Men/Women only (Neo/Quadro/Candela). Trio is no longer available. Do not use for other services.",
                        },
                        "machine_id": {
                            "type": "integer",
                            "description": "Only for service_id 1 or 12 after verified from get_machines. Omit for all other services.",
                        },
                        "branch_name": {"type": "string", "description": "Beirut or Antelias."},
                        "branch_id": {
                            "type": "integer",
                            "description": "Branch id from get_branches (commonly 1=Beirut, 3=Antelias; do not assume, use live list).",
                        },
                        "gender": {
                            "type": "string",
                            "enum": ["male", "female"],
                            "description": "Required for schedule rules if not already in session.",
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Full name in Latin for new CRM customers when file does not exist.",
                        },
                        "raw_user_date_text": {
                            "type": "string",
                            "description": ": original user wording for logs (e.g. tomorrow). Not used as execution source if date+time are set.",
                        },
                        "raw_user_time_text": {
                            "type": "string",
                            "description": ": original user time phrase for logs. Not execution source if time/date are resolved.",
                        },
                        "normalized_date": {"type": "string", "description": "If resolved, e.g. YYYY-MM-DD."},
                        "normalized_time": {
                            "type": "string",
                            "description": "If resolved, e.g. 15:00 or 3 PM phrasing already converted.",
                        },
                        "time": {
                            "type": "string",
                            "description": "Resolved clock time for execution when date is YYYY-MM-DD only, e.g. 09:00 or 17:30 (24h preferred).",
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Execution timezone; use Asia/Beirut unless the deployment specifies otherwise.",
                        },
                        "calendar_day_intent": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "description": " hint for debugging; do not rely on this alone for execution—send resolved date+time.",
                        },
                        "date_components": {
                            "type": "object",
                            "description": "Concrete civil datetime after resolving vague weekday phrases.",
                            "properties": {
                                "year": {"type": "integer"},
                                "month": {"type": "integer"},
                                "day": {"type": "integer"},
                                "hour": {"type": "integer"},
                                "minute": {"type": "integer"},
                            },
                        },
                        "date": {
                            "type": "string",
                            "description": "Execution date or full datetime: YYYY-MM-DD, or YYYY-MM-DD HH:MM:SS, or ISO-like string. "
                            "Must be absolute (no 'tomorrow' as the only value). Combine with time when passing date-only.",
                        },
                        "missing_fields": {"type": "array", "items": {"type": "string"}},
                        "ambiguities": {"type": "array", "items": {"type": "string"}},
                        "needs_clarification": {"type": "boolean"},
                        "confidence_notes": {"type": "array", "items": {"type": "string"}},
                        "execute_booking": {
                            "type": "boolean",
                            "description": "Default true: after validation, call CRM create. Set false to dry-run only.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_appointment",
                "description": (
                    "INTERNAL / LEGACY ONLY — do not call for normal new bookings. "
                    "Always use submit_booking_intent first; the server may still accept this tool for backward compatibility "
                    "but it runs the same CRM create step and returns the same structured success or validation-style failure "
                    "as submit_booking_intent (including when the calendar rejects the slot after local rules pass). "
                    "Requires phone, service_id, branch_id, date/time, and body_part_ids. "
                    "Only laser hair removal (1/12) uses customer-chosen device (get_machines: Neo/Quadro/Candela). Trio is no longer available. "
                    "For tattoo/CO2/whitening/hydrofacial/HIFU/etc. omit machine_id entirely. "
                    "NEVER use for reschedule when a paused appointment exists—use update_appointment_date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number, e.g., '71 123 456'."},
                        "service_id": {
                            "type": "integer",
                            "description": "Service ID: 1=Hair Men, 12=Hair Women, 2/11=CO2, 13=Tattoo, 4/5/14=Whitening. For female hair removal use 12, not 3.",
                        },
                        "machine_id": {
                            "type": "integer",
                            "description": "Only for hair removal service_id 1/12. Omit for tattoo/CO2/whitening/hydrofacial/HIFU/etc.",
                        },
                        "branch_id": {
                            "type": "integer",
                            "description": "Branch id from get_branches (commonly 1=Beirut, 3=Antelias; do not assume).",
                        },
                        "calendar_day_intent": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "description": "REQUIRED when the user spoke in relative day terms (اليوم، el yom، lyom، بكرا، bokra، tomorrow، etc.): set 'today' or 'tomorrow' exactly as you understood their intent. The server uses this with the clinic clock to lock the calendar day even if the ISO date in 'date' is wrong. Omit only when the user gave an explicit calendar date (e.g. 21/03/2026 or 'next Saturday' resolved by you to a specific day).",
                        },
                        "date_components": {
                            "type": "object",
                            "description": " but STRONGLY PREFERRED when the user used vague weekday phrases (الخميس الجاي، الجمعة الجاي، next Thursday…) or contradictory wording: after resolving to exactly ONE civil date using CALENDAR ANCHOR, pass year, month, day, hour (minute optional, default 0). Server builds API time from this first. If the user mentioned two different days, ask one clarification instead of guessing.",
                            "properties": {
                                "year": {"type": "integer", "description": "Gregorian year, e.g. 2026"},
                                "month": {"type": "integer", "description": "1-12"},
                                "day": {"type": "integer", "description": "1-31"},
                                "hour": {"type": "integer", "description": "0-23 (24h; 13 = 1 PM)"},
                                "minute": {"type": "integer", "description": "0-59; omit or 0 if not specified"},
                            },
                        },
                        # This is derived from the API Documentation PDF
                        "date": {
                            "type": "string",
                            "format": "date-time",
                            "description": "Full appointment date and time in 'YYYY-MM-DD HH:MM:SS' format (e.g., '2025-07-28 19:30:00'). Must match date_components when provided. Convert natural language using CURRENT DATE AND TIME / CALENDAR ANCHOR. For 'today'/'tomorrow' set calendar_day_intent. For next-Thursday-style phrases, prefer filling date_components.",
                        },
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "description": "**REQUIRED for all services** (hair, tattoo, CO2, whitening, etc.). Non-empty array of numeric body_part_id values from get_body_parts for the chosen service_id.",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "session_number": {
                                        "type": "integer",
                                        "description": "Use 1 for new/first-time bookings unless the user or CRM context says otherwise (2+ = follow-up session for that area).",
                                    },
                                },
                            },
                            "description": "; session numbers per area. Default create sends body_parts [{id, session_number}]. LINASLASER_APPOINTMENT_BODY_PART_IDS_ONLY=1 forces body_part_ids only when all sessions are 1.",
                        },
                    },
                    "required": ["phone", "service_id", "branch_id", "date", "body_part_ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_appointment_date",
                "description": (
                    "Updates the date/time of an existing appointment on the calendar. Use for reschedule/postpone/change to a NEW slot (Arabic «تأجيل الموعد»). "
                    "Same tool to put a PAUSED row onto a new datetime once the user chose the slot—this also covers phrasing like «يرجع يجي عالموعد», «كمّل الموعد», or 'resume the paused appointment'. Do NOT call pause_appointment for that. "
                    "If that row was PAUSED and the customer is continuing with it, do NOT leave it paused after this update. "
                    "You MUST pass the **exact appointment_id** the user selected (from check_next_appointment / customer_appointments JSON), plus structured **date**. "
                    "If multiple rows: first show each row to the user with appointment_id + service + machine + areas + price (if in JSON), ask them for the id (or line number), then call this tool. "
                    "Do NOT use pause_appointment to move to another day. "
                    "When the response is success=true, the Agent API accepted the change. The payload may include resume_appointment: after date update the server may POST a resume endpoint so Paused→Available—if resume_appointment.success is true, tell the user the slot is active at the new time; if resume failed or was skipped, datetime still changed but status may stay Paused until staff or API fixes it. Read hint_for_model."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "Numeric appointment id from CRM JSON (appointment_id / id)—the row the user chose to move or re-activate from pause.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Client's phone number (without country code), e.g., '71 123 456'.",
                        },
                        "calendar_day_intent": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "description": "When the user asked to move the appointment to 'today' or 'tomorrow' (اليوم، el yom، بكرا، etc.), set this so the server locks the correct day. Omit if they gave only an explicit calendar date.",
                        },
                        "date_components": {
                            "type": "object",
                            "description": "Same as create_appointment: optional structured year/month/day/hour/(minute) after you resolved the new slot; preferred for weekday-relative wording.",
                            "properties": {
                                "year": {"type": "integer"},
                                "month": {"type": "integer"},
                                "day": {"type": "integer"},
                                "hour": {"type": "integer"},
                                "minute": {"type": "integer"},
                            },
                        },
                        "date": {
                            "type": "string",
                            "format": "date-time",
                            "description": "New appointment date and time in 'YYYY-MM-DD HH:MM:SS' format (e.g., '2025-11-15 16:00:00'). Must match date_components when provided. Convert natural language; if relative day, set calendar_day_intent too.",
                        },
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                    },
                    "required": ["appointment_id", "phone", "date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resume_appointment",
                "description": (
                    "PRIMARY way to turn a **Paused** CRM row into **Available** again **without changing date/time**. "
                    "The backend calls CRM update-status with status_id=2 and both appointment_ids and appointment_id as the same int array (same slot). "
                    "Use when the customer wants the paused appointment active again: «رجّع الموعد», «خليه available», "
                    "«موقوف بدي يصير متاح», «فكّ البوز», «resume», same-slot reactivation. "
                    "You MUST pass the exact paused appointment_id from check_next_appointment / customer_appointments JSON. "
                    "If multiple paused rows exist, list them first, then call this tool with the chosen id. "
                    "Do NOT use this for a new calendar slot—for that use update_appointment_date. "
                    "Do NOT use pause_appointment from chat (it is disabled)—your role here is un-pause / re-activate, not pause."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "Paused appointment id to restore to Available.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Client phone number (local format accepted).",
                        },
                        "user_code": {
                            "type": "string",
                            "description": " compatibility field; ignored by current backend implementation.",
                        },
                    },
                    "required": ["appointment_id", "phone"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_paused_appointment",
                "description": (
                    "Advanced paused-appointment edit. Use when the user wants to modify a paused row details beyond date only "
                    "(body parts, session_number per part, machine, and/or explicit status to Available). "
                    "If the paused customer is continuing with this appointment, you MUST explicitly set `status` to `Available` in the same tool call so the row does not stay paused after the edit. "
                    "Pass appointment_id selected by the user. This executes one CRM update payload for that paused row. "
                    "After **success**, tell the user the **new session/total price** from the API response (or fetch via get_appointment_details). "
                    "If a **final agreed price** was already set with the customer for this appointment_id, call **sync_appointment_agreed_price** in the same turn (or immediately after) with that agreed_price so the system stays aligned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "integer", "description": "Paused appointment id to edit."},
                        "phone": {"type": "string", "description": "Client phone (local format accepted)."},
                        "date": {
                            "type": "string",
                            "format": "date-time",
                            "description": " new datetime YYYY-MM-DD HH:MM:SS.",
                        },
                        "machine_id": {"type": "integer", "description": " machine id (service-dependent)."},
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": " replacement body-part ids list.",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "session_number": {"type": "integer", "description": ">=1"},
                                },
                            },
                            "description": " per-body-part sessions. Preferred when session numbers matter.",
                        },
                        "status": {
                            "type": "string",
                            "description": " target status (e.g. Available). If omitted, server may default to Available for paused edits.",
                        },
                        "user_code": {"type": "string", "description": " user_code."},
                    },
                    "required": ["appointment_id", "phone"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_appointment",
                "description": (
                    "FULL update of an existing appointment per BOC API (POST /appointments/edit): "
                    "service, machine, branch, date, body_parts with per-area session_number, discounts. "
                    "Use when the user changes several fields at once or replaces body areas/sessions. "
                    "For **date-only** reschedule prefer update_appointment_date. "
                    "If the edited row is PAUSED and the customer is continuing with it, do NOT use this tool alone: also call `resume_appointment` in the same turn so the appointment becomes Available again. "
                    "Either phone OR user_code required. Do not send root session_number together with body_parts unless the API requires it. "
                    "After **success**, always communicate the **new session/total price** to the user (from response JSON or get_appointment_details). "
                    "If you had an **agreed final price** with the customer for this appointment_id, call **sync_appointment_agreed_price** with the same agreed_price so CRM discount matches after body/machine changes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "integer", "description": "CRM appointment id to edit."},
                        "phone": {
                            "type": "string",
                            "description": "Customer phone (local format); required if user_code omitted.",
                        },
                        "user_code": {"type": "string", "description": "Customer code; required if phone omitted."},
                        "service_id": {"type": "integer", "description": " new service id."},
                        "machine_id": {"type": "integer", "description": " new machine id."},
                        "branch_id": {"type": "integer", "description": " new branch id."},
                        "date": {
                            "type": "string",
                            "description": " new datetime YYYY-MM-DD HH:MM:SS (must be future).",
                        },
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "; if body_parts_with_sessions omitted, builds body_parts with same session_number.",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "id": {"type": "integer", "description": "Same as body_part_id if you prefer."},
                                    "session_number": {"type": "integer"},
                                },
                            },
                            "description": "Replace appointment body areas; API uses body_parts[].id + session_number.",
                        },
                        "session_number": {
                            "type": "integer",
                            "description": "Use only when NOT sending body_parts; applies with body_part_ids fallback.",
                        },
                        "discount_percentage": {"type": "number"},
                        "discount_amount": {"type": "number"},
                        "total_cost_after_discount": {"type": "number"},
                        "hidden": {"type": "boolean"},
                    },
                    "required": ["appointment_id"],
                },
            },
        },
]
