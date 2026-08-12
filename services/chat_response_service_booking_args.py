"""Legacy GPT chat-response helpers group 5."""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Iterator
from typing import Any

import config
from services.chat_response_service_booking_name import _service_hint_to_service_id
from services.chat_response_service_constants import (
    BOOKING_TZ,
    HAIR_REMOVAL_MACHINE_IDS,
    _safe_int,
)
from utils.datetime_utils import (
    align_datetime_to_day_reference,
    datetime_from_ai_date_components,
    detect_existing_appointment_edit_intent,
    now_in_bot_tz,
    parse_datetime_flexible,
)


def _extract_json_objects(raw: str) -> Iterator[str]:
    """
    Extract all complete JSON objects from a string. GPT sometimes returns multiple objects:
    - First: preferred_service, preferred_branch, etc. (no action/bot_reply)
    - Second: action, bot_reply (the actual response)
    Yields (start, end) slices for each object.
    """
    s = (raw or "").strip()
    pos = 0
    while pos < len(s):
        # Find next {
        idx = s.find("{", pos)
        if idx < 0:
            break
        depth = 0
        in_string = False
        escape = False
        i = idx
        while i < len(s):
            c = s[i]
            if escape:
                escape = False
                i += 1
                continue
            if c == "\\" and in_string:
                escape = True
                i += 1
                continue
            if not in_string:
                if c == '"':
                    in_string = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        yield s[idx : i + 1]
                        pos = i + 1
                        break
            else:
                if c == '"':
                    in_string = False
            i += 1
        else:
            break

def _dedupe_bot_reply_text(text: str) -> str:
    """
    Models sometimes echo the same user-visible text twice, or concatenate two identical JSON blobs
    inside bot_reply. Collapse so WhatsApp users see a single message.
    """
    s = (text or "").strip()
    if not s:
        return s
    n = len(s)
    if n >= 24 and n % 2 == 0 and s[: n // 2] == s[n // 2 :]:
        return s[: n // 2].strip()
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    if len(lines) == 2 and lines[0] == lines[1]:
        return lines[0]
    if s.startswith("{") and '"action"' in s:
        parts = list(_extract_json_objects(s))
        if len(parts) >= 2:
            try:
                d0 = json.loads(parts[0])
                d1 = json.loads(parts[1])
                if isinstance(d0, dict) and isinstance(d1, dict):
                    b0 = (d0.get("bot_reply") or "").strip()
                    b1 = (d1.get("bot_reply") or "").strip()
                    if b0 and b0 == b1:
                        return b0
                    if b0:
                        return b0
            except (json.JSONDecodeError, TypeError):
                pass
    return s

def _parse_gpt_response_json(raw: str) -> dict:
    """
    Parse GPT response that may contain multiple JSON objects. Returns the first object
    that has both action and bot_reply. GPT sometimes returns two objects:
    - First: preferred_service, preferred_branch, etc. (no action/bot_reply)
    - Second: action, bot_reply (the actual response)
    It may also emit the same JSON object twice; duplicates are collapsed.
    """
    matches: list[dict[str, Any]] = []
    for obj_str in _extract_json_objects(raw):
        try:
            parsed = json.loads(obj_str)
            # Require action + bot_reply key; allow empty bot_reply (models sometimes emit "" with a tool blob above).
            if isinstance(parsed, dict) and parsed.get("action") is not None and "bot_reply" in parsed:
                br = _dedupe_bot_reply_text(str(parsed.get("bot_reply") or ""))
                if not (br or "").strip():
                    br = "عذراً، لم يُكتمل نص الرد تلقائياً. جرّب مرة ثانية أو تواصل مع الفرع."
                parsed = {**parsed, "bot_reply": br}
                matches.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue
    if not matches:
        raise json.JSONDecodeError("No valid JSON object with action and bot_reply found", raw, 0)
    if len(matches) == 1:
        return matches[0]
    sigs = [json.dumps(m, sort_keys=True, ensure_ascii=False, default=str) for m in matches]
    if len(set(sigs)) == 1:
        return matches[0]
    return matches[0]

def _extract_preferred_booking_from_gpt(raw: str) -> dict:
    """
    Extract preferred_* fields from GPT response (first JSON object). Used by booking fallback
    to populate machine_id and body_part_ids when GPT returns confirmation but didn't call the tool.
    """
    out: dict[str, Any] = {}
    for obj_str in _extract_json_objects(raw):
        try:
            parsed = json.loads(obj_str)
            if not isinstance(parsed, dict):
                continue
            if parsed.get("preferred_machine_id") is not None:
                out["preferred_machine_id"] = _safe_int(parsed.get("preferred_machine_id"))
            if parsed.get("preferred_area"):
                out["preferred_area"] = str(parsed.get("preferred_area", "")).strip()
            if parsed.get("preferred_service"):
                out["preferred_service"] = str(parsed.get("preferred_service", "")).strip()
            if parsed.get("preferred_branch"):
                out["preferred_branch"] = str(parsed.get("preferred_branch", "")).strip()
            if out:
                return out
        except (json.JSONDecodeError, TypeError):
            continue
    return out

def _extract_booking_args_from_gpt_raw(raw: str) -> dict:
    """
    Parse tool-style JSON blobs emitted before the action JSON (e.g. date/time/service/machine)
    when the model confirms booking in text but does not call create_appointment.
    """
    out: dict[str, Any] = {}
    for obj_str in _extract_json_objects(raw or ""):
        try:
            parsed = json.loads(obj_str)
            if not isinstance(parsed, dict):
                continue
            if parsed.get("action") is not None and "bot_reply" in parsed:
                continue
            for k in (
                "date",
                "time",
                "machine_id",
                "service_id",
                "service",
                "branch",
                "branch_id",
                "body_part",
                "body_part_text",
                "phone",
                "body_part_ids",
                "body_parts",
                "date_components",
                "calendar_day_intent",
                "customer_phone",
                "detected_name",
                "customer_name",
                "execute_booking",
                "gender",
            ):
                if k in parsed and parsed[k] is not None:
                    out[k] = parsed[k]
        except (json.JSONDecodeError, TypeError):
            continue
    if not out.get("body_part") and out.get("body_part_text"):
        out["body_part"] = str(out.get("body_part_text") or "").strip()
    # GPT often splits clock into separate "time" — recovery normalize expects one "date" string.
    if out.get("date") is not None and out.get("time"):
        ds = str(out["date"]).strip()
        ts = str(out["time"]).strip()
        if ds and ts and "T" not in ds and not re.search(r"\b\d{1,2}:\d{2}\b", ds):
            out["date"] = f"{ds} {ts}".strip()
        out.pop("time", None)
    return out

def _detect_change_request_intent(user_text: str) -> bool:
    text = str(user_text or "").strip().lower()
    if not text:
        return False
    change_patterns = [
        r"\b(reschedule|rescheduling|postpone|postponing|push back|move appointment|change appointment|shift appointment)\b",
        r"\b(reporter|decaler|décaler|deplacer|déplacer|changer rendez[- ]?vous)\b",
        r"(تأجيل|اجل|أجل|أجّل|تغيير الموعد|غير الموعد|غيّر الموعد|نقل الموعد|تبديل الموعد|موعد تاني|موعد اخر|موعد آخر)",
        r"\b(2ajel|ajjel|ghayer el maw3ed|ghayer maw3ed|postpone el maw3ed|reschedule el maw3ed)\b",
    ]
    return any(re.search(pattern, text, re.IGNORECASE | re.UNICODE) for pattern in change_patterns) or (
        detect_existing_appointment_edit_intent(text)
    )

def _collect_recent_user_text_for_change_intent(
    context_messages: list[dict] | None, latest_user_input: str, max_parts: int = 15
) -> str:
    parts: list[str] = []
    for msg in (context_messages or [])[-24:]:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    latest_clean = (latest_user_input or "").strip()
    if latest_clean and (not parts or parts[-1] != latest_clean):
        parts.append(latest_clean)
    return " ".join(parts[-max_parts:]).strip()

def _normalize_booking_date_for_tool_args(function_args: dict) -> tuple[bool, str | None]:
    """
    Same rules as inline normalize_tool_date for create/update, without touching api_failure_reason.
    Mutates function_args (pops calendar_day_intent, date_components); sets date API string.
    Returns (ok: bool, error_code: str | None).
    """
    if not function_args.get("date") and not function_args.get("date_components"):
        return False, "booking_date_missing_field"
    original_date_str = str(function_args.get("date") or "").strip()
    now = now_in_bot_tz()
    ai_day_raw = function_args.pop("calendar_day_intent", None)
    dc_raw = function_args.pop("date_components", None)
    forced_day_ref = None
    if isinstance(ai_day_raw, str) and ai_day_raw.strip().lower() in ("today", "tomorrow"):
        forced_day_ref = ai_day_raw.strip().lower()

    dt_obj = datetime_from_ai_date_components(dc_raw)
    if dt_obj is not None:
        pass
    else:
        if not original_date_str:
            return False, "booking_structured_date_invalid"
        dt_obj = parse_datetime_flexible(original_date_str)
        if not dt_obj:
            return False, "booking_date_parse_failed"
        if forced_day_ref in ("today", "tomorrow"):
            dt_obj = align_datetime_to_day_reference(dt_obj, forced_day_ref, reference=now)

    if dt_obj.year < now.year:
        dt_obj = dt_obj.replace(year=now.year)

    max_allowed = now + datetime.timedelta(days=365)
    if dt_obj > max_allowed:
        return False, "booking_date_out_of_window"
    if dt_obj <= now:
        return False, "booking_date_in_past_or_now"

    function_args["date"] = dt_obj.astimezone(BOOKING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return True, None

def _bot_reply_claims_completed_booking(bot_reply: str) -> bool:
    """True if the assistant text tells the user a NEW booking was completed (CRM must have confirmed)."""
    br = (bot_reply or "").strip().lower()
    if not br:
        return False
    # Keep in sync with the booking_claimed_without_* guard below. Models vary wording
    # (e.g. «صار الحجز مُثبت») — all must be caught to avoid false «booked» without tools.
    return any(
        x in br
        for x in (
            "تم تثبيت",
            "تمّ تثبيت",
            "تم حجز",
            "تمّ حجز",
            "صار الحجز",
            "صار موعدك",
            "الحجز مُثبت",
            "الحجز مثبت",
            "حجز مُثبت",
            "حجز مثبت",
            "تم تأكيد الحجز",
            "تمّ تأكيد الحجز",
            "تأكيد حجزك",
            "حجزك تم",
            "تم حجزك",
            "booked successfully",
            "appointment has been booked",
            "your appointment is confirmed",
            "appointment is confirmed",
        )
    )

def _parse_tool_round_bot_returned_local(bot_returned: str) -> Any:
    if not bot_returned or not isinstance(bot_returned, str):
        return None
    try:
        return json.loads(bot_returned)
    except (json.JSONDecodeError, TypeError):
        return None

def _latest_successful_update_date_from_tool_rounds(tool_round_trips: list[dict[str, Any]]) -> str | None:
    """Return the most recent CRM new_date from a successful appointment date/update tool."""
    for tr in reversed(tool_round_trips or []):
        name = str(tr.get("ai_requested") or "").strip()
        if name not in ("update_appointment_date", "update_paused_appointment", "edit_appointment"):
            continue
        returned = _parse_tool_round_bot_returned_local(tr.get("bot_returned") or "")
        if not isinstance(returned, dict) or not returned.get("success"):
            continue
        data_raw = returned.get("data")
        data = data_raw if isinstance(data_raw, dict) else {}
        new_date = data.get("new_date") or data.get("date") or returned.get("new_date")
        if new_date:
            return str(new_date)
    return None

def _partial_paused_date_update_reply(language: str, new_date: str | None) -> str:
    """User-facing fallback when date changed but pause/Available status did not confirm."""
    when = f" إلى {new_date}" if new_date else ""
    if language == "en":
        return (
            f"The appointment time was updated in the system{(' to ' + new_date) if new_date else ''}. "
            "The API did not confirm removing the pause status, so if reception still sees it as paused, they need to clear it manually."
        )
    if language == "fr":
        return (
            f"L'heure du rendez-vous a été modifiée dans le système{(' à ' + new_date) if new_date else ''}. "
            "L'API n'a pas confirmé la suppression du statut pause; si la réception le voit encore en pause, elle doit le réactiver manuellement."
        )
    return (
        f"الوقت اتعدّل على السيستم{when}. "
        "حالة البوز ما تأكد تغييرها من الـ API، فإذا بقيت ظاهرة عند الاستقبال بدها متابعة يدوية."
    )

def _extract_submit_booking_failure_details(tool_round_trips: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the last submit_booking_intent failure with structured details for loop guard logs."""
    last_detail: dict[str, Any] | None = None
    for tr in tool_round_trips or []:
        name = str(tr.get("ai_requested") or "").strip()
        if name != "submit_booking_intent":
            continue
        bot_returned = _parse_tool_round_bot_returned_local(tr.get("bot_returned") or "")
        if not isinstance(bot_returned, dict) or bot_returned.get("success") is True:
            continue
        last_detail = {
            "tool_name": name,
            "error_type": bot_returned.get("error_type"),
            "human_readable_reason": bot_returned.get("human_readable_reason"),
            "missing_fields": bot_returned.get("missing_fields") or [],
            "invalid_fields": bot_returned.get("invalid_fields") or {},
            "conflicting_fields": bot_returned.get("conflicting_fields") or {},
            "normalized_values": bot_returned.get("normalized_values") or {},
            "activity_trace": bot_returned.get("activity_trace") or {},
            "tool_args": tr.get("args"),
            "backend_execution": tr.get("backend_execution") or {},
        }
    return last_detail

def _resolve_branch_id_from_leak(leaked: dict) -> int | None:
    bid = _safe_int(leaked.get("branch_id"))
    if bid in (1, 2):
        return bid
    br = str(leaked.get("branch") or "").strip().lower()
    if "beirut" in br or "بيروت" in br:
        return 1
    if "antelias" in br or "انطلياس" in br or "antaliyas" in br:
        return 2
    return None

def _infer_service_id_from_leak(leaked: dict, current_gender: str) -> int:
    sid = _safe_int(leaked.get("service_id"))
    mid = _safe_int(leaked.get("machine_id"))
    if sid == 13 and mid is not None and mid in HAIR_REMOVAL_MACHINE_IDS:
        return 12 if current_gender == "female" else 1
    if sid is not None:
        return sid
    hint_sid = _service_hint_to_service_id(leaked.get("service"))
    if hint_sid is not None:
        return hint_sid
    svc = str(leaked.get("service") or "").strip().lower()
    if "hair" in svc or "شعر" in svc or "laser hair" in svc:
        return 12 if current_gender == "female" else 1
    return int(config.DEFAULT_SERVICE_ID or 1)

