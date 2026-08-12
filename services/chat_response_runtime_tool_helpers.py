"""Nested tool-loop helpers bound onto ns."""

from __future__ import annotations

from services.chat_response_runtime_common import (
    BOOKING_TZ,
    Any,
    _extract_customer_appointments_list,
    _is_paused_like_appointment_status,
    align_datetime_to_day_reference,
    api_integrations,
    datetime,
    datetime_from_ai_date_components,
    detect_existing_appointment_edit_intent,
    detect_last_weekday_intent_from_user_text,
    next_future_datetime_matching_weekday,
    now_in_bot_tz,
    parse_datetime_flexible,
    re,
)


def bind_tool_helpers(ns: Any) -> None:
    def normalize_phone_for_lookup(raw_phone: str) -> str:
        if not raw_phone:
            return ""
        normalized = str(raw_phone).replace("+", "").replace(" ", "").replace("-", "")
        if normalized.startswith("961"):
            normalized = normalized[3:]
        return normalized

    def extract_appointment_id(appointment_payload: dict) -> Any:
        if not isinstance(appointment_payload, dict):
            return None
        for key in ("appointment_id", "id", "appointmentId"):
            value = appointment_payload.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def extract_appointment_status(appointment_payload: dict) -> str:
        if not isinstance(appointment_payload, dict):
            return ""

        raw_status = (
            appointment_payload.get("status")
            or appointment_payload.get("appointment_status")
            or appointment_payload.get("appointmentStatus")
            or appointment_payload.get("state")
            or appointment_payload.get("appointment_state")
        )

        if isinstance(raw_status, dict):
            raw_status = raw_status.get("name") or raw_status.get("status")

        return str(raw_status or "").strip()

    def is_paused_status(status_value: str) -> bool:
        return _is_paused_like_appointment_status(str(status_value or ""))

    def extract_check_next_appointment(response_payload: dict) -> dict:
        if not isinstance(response_payload, dict):
            return {}
        data = response_payload.get("data")
        if isinstance(data, dict):
            appointment_payload = data.get("appointment")
            if isinstance(appointment_payload, dict):
                return appointment_payload
            # Some APIs return the appointment directly under data
            if ns.extract_appointment_id(data):
                return data
        return {}

    def extract_customer_appointments(response_payload: dict) -> list:
        return _extract_customer_appointments_list(response_payload)

    def detect_change_request_intent(user_text: str) -> bool:
        text = str(user_text or "").strip().lower()
        if not text:
            return False

        change_patterns = [
            r"\b(reschedule|rescheduling|postpone|postponing|push back|move appointment|change appointment|shift appointment)\b",
            r"\b(resume|reactivate|bring back|continue)\b.{0,30}\b(appointment|slot)\b",
            r"\b(reporter|decaler|décaler|deplacer|déplacer|changer rendez[- ]?vous)\b",
            r"(تأجيل|اجل|أجل|أجّل|تغيير الموعد|غير الموعد|غيّر الموعد|نقل الموعد|تبديل الموعد|موعد تاني|موعد اخر|موعد آخر)",
            r"(?:رج[ّ]?ع|ارجع|يرجع|كم[ّ]?ل|كمل|فك|شيل).{0,35}(?:الموعد|موعدي|موعد|الموقوف|موقوف|البوز)",
            r"(?:رج[ّ]?ع|ارجع|يرجع).{0,12}(?:يجي|جي).{0,24}(?:على|ع)\s*(?:الموعد|موعدي|موعد)",
            r"\b(2ajel|ajjel|ghayer el maw3ed|ghayer maw3ed|postpone el maw3ed|reschedule el maw3ed)\b",
            r"\b(rj+3|rje3|rja3|rod|rudd|kamm?el|kmel|fokk|fok|shil)\b.{0,30}\b(mw3ad|maw3ad|mou3ad|boz|pause|paused)\b",
            r"\b(rj+3|rje3|rja3)\b.{0,10}\b(yje|yeje|iji|yiji|ji)\b.{0,20}\b(3a|3al|aal|al)\b.{0,8}\b(mw3ad|maw3ad|mou3ad)\b",
        ]
        return any(re.search(pattern, text, re.IGNORECASE | re.UNICODE) for pattern in change_patterns) or (
            detect_existing_appointment_edit_intent(text)
        )

    async def find_paused_appointment_id(phone_to_lookup: str) -> Any:
        pass  # ns-bound check_next_appointment_result
        normalized_phone = ns.normalize_phone_for_lookup(phone_to_lookup)
        if not normalized_phone:
            return None

        if normalized_phone in ns.paused_appointment_lookup_cache:
            return ns.paused_appointment_lookup_cache[normalized_phone]

        paused_appointment_id = None

        # First check the dedicated "next appointment" endpoint.
        try:
            next_result = await api_integrations.check_next_appointment(phone=normalized_phone)
            if isinstance(next_result, dict) and next_result.get("success"):
                ns.check_next_appointment_result = next_result
                next_appointment_payload = ns.extract_check_next_appointment(next_result)
                if ns.is_paused_status(ns.extract_appointment_status(next_appointment_payload)):
                    paused_appointment_id = ns.extract_appointment_id(next_appointment_payload)
        except Exception as pause_next_error:
            print(f"WARNING: Paused guard check_next_appointment failed for {normalized_phone}: {pause_next_error}")

        # Fallback: scan all customer appointments for paused records.
        if not paused_appointment_id:
            try:
                customer_appointments = await api_integrations.get_customer_appointments(phone=normalized_phone)
                if isinstance(customer_appointments, dict) and customer_appointments.get("success"):
                    for appointment_payload in ns.extract_customer_appointments(customer_appointments):
                        if ns.is_paused_status(ns.extract_appointment_status(appointment_payload)):
                            paused_appointment_id = ns.extract_appointment_id(appointment_payload)
                            if paused_appointment_id:
                                break
            except Exception as pause_list_error:
                print(
                    f"WARNING: Paused guard get_customer_appointments failed for {normalized_phone}: {pause_list_error}"
                )

        ns.paused_appointment_lookup_cache[normalized_phone] = paused_appointment_id
        return paused_appointment_id

    async def list_paused_appointment_ids(phone_to_lookup: str) -> list:
        normalized_phone = ns.normalize_phone_for_lookup(phone_to_lookup)
        if not normalized_phone:
            return []
        out: list = []
        try:
            customer_appointments = await api_integrations.get_customer_appointments(phone=normalized_phone)
            if isinstance(customer_appointments, dict) and customer_appointments.get("success"):
                for appointment_payload in ns.extract_customer_appointments(customer_appointments):
                    if ns.is_paused_status(ns.extract_appointment_status(appointment_payload)):
                        aid = ns.extract_appointment_id(appointment_payload)
                        if aid is not None:
                            try:
                                out.append(int(aid))
                            except (TypeError, ValueError):
                                pass
        except Exception as list_p_e:
            print(f"WARNING: list_paused_appointment_ids failed: {list_p_e}")
        return out

    def collect_user_datetime_text(context_messages: list, latest_user_input: str) -> str:
        """
        Collect recent user text for date intent detection.
        Keeps chronology and ends with latest user input so the newest
        'today/tomorrow' intent wins over stale history.
        """
        recent_user_messages = []
        for msg in context_messages[-24:]:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                recent_user_messages.append(content.strip())

        # Keep recent user turns (wider window: weekday + id-only replies stay linked).
        recent_user_messages = recent_user_messages[-30:]

        latest_clean = (latest_user_input or "").strip()
        if latest_clean and (not recent_user_messages or recent_user_messages[-1] != latest_clean):
            recent_user_messages.append(latest_clean)

        return " ".join(recent_user_messages).strip()

    def collect_recent_user_only_schedule_text(
        context_messages: list, latest_user_input: str, max_user_messages: int = 40
    ) -> str:
        """User messages only (no assistant lists) — for weekday intent when user sends id-only reply."""
        recent_user_messages = []
        for msg in context_messages[-100:]:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                recent_user_messages.append(content.strip())
        recent_user_messages = recent_user_messages[-max_user_messages:]
        latest_clean = (latest_user_input or "").strip()
        if latest_clean and (not recent_user_messages or recent_user_messages[-1] != latest_clean):
            recent_user_messages.append(latest_clean)
        return " ".join(recent_user_messages).strip()

    def normalize_tool_date(
        function_name: str,
        function_args: dict,
        *,
        user_input_for_date: str | None = None,
        context_messages_for_date: list | None = None,
    ) -> bool:
        """
        Build API datetime from AI tool arguments only (date_components, date string,
        calendar_day_intent). Does not parse user chat text. False → handover (flow_meta.error).
        """
        pass  # ns-bound api_failure_reason
        if "date" not in function_args:
            ns.api_failure_reason = "booking_date_missing_field"
            return False

        original_date_str = str(function_args.get("date") or "").strip()
        now = now_in_bot_tz()
        ai_day_raw = function_args.pop("calendar_day_intent", None)
        dc_raw = function_args.pop("date_components", None)
        forced_day_ref = None
        if isinstance(ai_day_raw, str) and ai_day_raw.strip().lower() in ("today", "tomorrow"):
            forced_day_ref = ai_day_raw.strip().lower()

        dt_obj = datetime_from_ai_date_components(dc_raw)
        if dt_obj is not None:
            print(f"DEBUG: Using date_components for {function_name}: {dc_raw} -> {dt_obj}")
        else:
            if not original_date_str:
                print(f"WARNING: {function_name}: missing date_components and empty date string.")
                ns.api_failure_reason = "booking_structured_date_invalid"
                return False
            dt_obj = parse_datetime_flexible(original_date_str)
            if not dt_obj:
                print(f"WARNING: Could not parse AI date '{original_date_str}' for {function_name}.")
                ns.api_failure_reason = "booking_date_parse_failed"
                return False
            if forced_day_ref in ("today", "tomorrow"):
                dt_obj = align_datetime_to_day_reference(dt_obj, forced_day_ref, reference=now)

        # Reschedule: user named a weekday then sent only appointment_id — model often keeps the old slot's day and changes hour only.
        if (
            function_name in ("update_appointment_date", "edit_appointment")
            and user_input_for_date is not None
            and context_messages_for_date is not None
        ):
            uid = (user_input_for_date or "").strip()
            if re.fullmatch(r"\d{4,7}", uid):
                u_sched = ns.collect_recent_user_only_schedule_text(
                    context_messages_for_date, user_input_for_date, max_user_messages=40
                )
                tw = detect_last_weekday_intent_from_user_text(u_sched)
                if tw is not None and dt_obj.weekday() != tw:
                    adjusted = next_future_datetime_matching_weekday(now, tw, dt_obj.hour, dt_obj.minute)
                    if adjusted is not None:
                        print(
                            f"SAFETY: update_appointment_date weekday align {dt_obj} -> {adjusted} "
                            f"(user id-only; thread weekday={tw})"
                        )
                        dt_obj = adjusted

        if dt_obj.year < now.year:
            dt_obj = dt_obj.replace(year=now.year)
            print(f"WARNING: AI date year adjusted to current year: {dt_obj}")

        max_allowed = now + datetime.timedelta(days=365)
        if dt_obj > max_allowed:
            print(f"WARNING: AI date beyond allowed window: {dt_obj}")
            ns.api_failure_reason = "booking_date_out_of_window"
            return False
        if dt_obj <= now:
            print(f"WARNING: AI date not strictly in the future: {dt_obj} (now={now})")
            ns.api_failure_reason = "booking_date_in_past_or_now"
            return False

        function_args["date"] = dt_obj.astimezone(BOOKING_TZ).strftime("%Y-%m-%d %H:%M:%S")
        print(f"DEBUG: Normalized date for {function_name}: {original_date_str or dc_raw} -> {function_args['date']}")
        return True

    ns.normalize_phone_for_lookup = normalize_phone_for_lookup
    ns.extract_appointment_id = extract_appointment_id
    ns.extract_appointment_status = extract_appointment_status
    ns.is_paused_status = is_paused_status
    ns.extract_check_next_appointment = extract_check_next_appointment
    ns.extract_customer_appointments = extract_customer_appointments
    ns.detect_change_request_intent = detect_change_request_intent
    ns.find_paused_appointment_id = find_paused_appointment_id
    ns.list_paused_appointment_ids = list_paused_appointment_ids
    ns.collect_user_datetime_text = collect_user_datetime_text
    ns.collect_recent_user_only_schedule_text = collect_recent_user_only_schedule_text
    ns.normalize_tool_date = normalize_tool_date
