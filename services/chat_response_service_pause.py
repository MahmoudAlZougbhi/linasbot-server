"""Legacy GPT chat-response helpers group 3."""

from __future__ import annotations

import re
from typing import Any

from services.chat_response_service_appointments import (
    _appointment_numeric_id,
    _arabic_indic_digits_to_ascii,
    _customer_appointments_embedded_in_payload,
)
from services.chat_response_service_constants import (
    CLINIC_PRICE_CONTEXT_KEYWORDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    OFF_TOPIC_PRICE_FALSE_POSITIVE_HINTS,
    PRICE_STRONG_KEYWORDS,
    PRICE_WEAK_KEYWORDS,
    _normalize_body_part_ids,
    _safe_int,
)
from services.chat_response_service_pricing import _get_body_part_required_service_ids
from services.chat_response_service_profile import (
    _extract_customer_appointments_list,
    _filter_appointments_for_reschedule_overview,
    _is_paused_like_appointment_status,
)


def _ordered_paused_appointments_from_snapshot(payload: dict | None) -> list[dict]:
    """Stable CRM order: paused rows only, deduped by id (check_next enrich or get_customer_appointments)."""
    if not isinstance(payload, dict):
        return []
    rows = _customer_appointments_embedded_in_payload(payload)
    if not rows:
        rows = _extract_customer_appointments_list(payload)
    rows = _filter_appointments_for_reschedule_overview(rows)
    out: list[dict] = []
    seen: set = set()
    for apt in rows:
        st = str(apt.get("status") or apt.get("appointment_status") or "")
        if not _is_paused_like_appointment_status(st):
            continue
        aid = _appointment_numeric_id(apt)
        if aid is None or aid in seen:
            continue
        seen.add(aid)
        out.append(apt)
    return out

def _resolve_user_chosen_paused_appointment_id(user_text: str, paused_ids: list[int]) -> int | None:
    """
    After the bot listed paused rows 1..N, map the user's reply to the CRM appointment_id.
    Avoids treating '3' inside a long datetime sentence as a list index (length + pattern guards).
    """
    if not user_text or not paused_ids:
        return None
    n = len(paused_ids)
    t_raw = user_text.strip()
    t = _arabic_indic_digits_to_ascii(t_raw)

    for aid in sorted(set(paused_ids), reverse=True):
        if re.search(rf"(?<!\d){int(aid)}(?!\d)", t):
            return int(aid)

    m2 = re.search(
        r"(?:رقم|number|#|اختر|اختار|choice|option|n\s*)\s*(\d{1,2})\b",
        t,
        re.I,
    )
    if m2:
        idx = int(m2.group(1))
        if 1 <= idx <= n:
            return paused_ids[idx - 1]

    m1 = re.match(r"^[\s#]*(\d{1,2})[\s.):،,-]*$", t)
    if m1 and len(t) <= 22:
        idx = int(m1.group(1))
        if 1 <= idx <= n:
            return paused_ids[idx - 1]

    return None

def _bot_reply_claims_completed_appointment_update(bot_reply: str) -> bool:
    br = (bot_reply or "").strip().lower()
    if "تم تثبيت تعديل" in br or "تمّ تثبيت تعديل" in br:
        return True
    if "تم تثبيت طلبك" in br and ("تعديل" in br or "موعد" in br):
        return True
    if "تم تأكيد التعديل" in br or "تم تأكيد تعديل" in br:
        return True
    if "appointment has been updated" in br or "appointment has been rescheduled" in br:
        return True
    if "تم تحديث الموعد" in br or "تم نقل الموعد" in br:
        return True
    return False

def validate_language_match(user_language: str, bot_response: str, detected_response_lang: str) -> tuple:
    """
    Validate bot response matches user language
    Returns: (is_valid: bool, error_message: str)
    """
    # Character patterns for each language
    patterns = {
        "ar": r"[\u0600-\u06FF]",  # Arabic
        "en": r"[a-zA-Z]",
        "fr": r"[a-zA-Z]",
    }

    # Franco should get Arabic response
    if user_language == "franco":
        user_language = "ar"

    # For Arabic responses, enforce Arabic script only (names included).
    # Allow URLs/emails to pass untouched when needed.
    if user_language == "ar":
        sanitized = re.sub(
            r"https?://\S+|www\.\S+|\b\S+@\S+\b",
            "",
            bot_response or "",
            flags=re.IGNORECASE,
        )
        if re.search(r"[A-Za-z]", sanitized):
            return False, "Language mismatch: Arabic response contains Latin letters."

    if user_language not in patterns:
        return True, ""  # Skip validation for unknown languages

    # Count characters matching expected language
    expected_chars = len(re.findall(patterns[user_language], bot_response))
    total_chars = len(re.sub(r"\s", "", bot_response))  # Exclude spaces

    if total_chars == 0:
        return True, ""

    match_ratio = expected_chars / total_chars

    if match_ratio < 0.7:  # 70% threshold
        return False, f"Language mismatch: {match_ratio:.1%} match (expected ≥70% {user_language})"

    return True, ""

def _contains_arabic_script(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(text or "")))

def looks_like_working_hours_reply(text: str) -> bool:
    """Heuristic: detect replies that are clearly about clinic hours/opening times."""
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    hours_patterns = [
        r"\bworking\s+hours\b",
        r"\bopening\s+hours\b",
        r"\bopen\s+from\b",
        r"\bclinic\s+hours\b",
        r"(?:ساعات\s*(?:العمل|الدوام)|اوقات\s*العمل|دوامنا|الدوام)",
        r"\bhoraires\b",
        r"\bouvert\b",
    ]
    return any(re.search(pattern, normalized, re.IGNORECASE | re.UNICODE) for pattern in hours_patterns)

def is_price_related_question(text: str, booking_state: dict[str, Any] | None = None) -> bool:
    normalized = str(text or "").lower()
    if not normalized.strip():
        return False

    has_strong_price_signal = any(keyword in normalized for keyword in PRICE_STRONG_KEYWORDS)
    has_weak_price_signal = any(keyword in normalized for keyword in PRICE_WEAK_KEYWORDS)
    if not has_strong_price_signal and not has_weak_price_signal:
        return False

    has_clinic_context = any(keyword in normalized for keyword in CLINIC_PRICE_CONTEXT_KEYWORDS)
    state = booking_state or {}
    has_booking_context = any(
        [
            state.get("service_id"),
            state.get("machine_id"),
            state.get("branch_id"),
            state.get("body_part_ids"),
            state.get("last_pricing_payload"),
        ]
    )
    looks_off_topic = any(keyword in normalized for keyword in OFF_TOPIC_PRICE_FALSE_POSITIVE_HINTS)

    # Prevent false positives like "kam dawle..." from triggering pricing sync.
    if looks_off_topic and not has_clinic_context and not has_booking_context:
        return False

    if has_strong_price_signal:
        return True

    # Weak signals (kam/adde/قديش) need either clinic context or active booking context.
    return has_clinic_context or has_booking_context

def _booking_submit_payload_complete_for_execution(function_args: dict[str, Any], current_gender: str) -> bool:
    """True when submit_booking_intent has enough concrete values to execute without a recap round-trip."""
    if not isinstance(function_args, dict):
        return False
    if function_args.get("needs_clarification") is True:
        return False
    if function_args.get("execute_booking") is False:
        return False

    sid = _safe_int(function_args.get("service_id"))
    bid = _safe_int(function_args.get("branch_id"))
    mid = _safe_int(function_args.get("machine_id"))
    gender = str(function_args.get("gender") or current_gender or "").strip().lower()
    if sid is None or bid is None or gender not in ("male", "female"):
        return False
    if sid in LASER_HAIR_REMOVAL_SERVICE_IDS and mid is None:
        return False

    body_ids = _normalize_body_part_ids(function_args.get("body_part_ids"))
    session_rows = function_args.get("body_parts_with_sessions")
    has_session_rows = isinstance(session_rows, list) and bool(session_rows)
    if sid in _get_body_part_required_service_ids() and not (body_ids or has_session_rows):
        return False

    has_datetime = bool(function_args.get("date_components")) or bool(function_args.get("date"))
    if not has_datetime:
        has_datetime = bool(
            (function_args.get("normalized_date") or function_args.get("raw_user_date_text"))
            and (
                function_args.get("normalized_time")
                or function_args.get("time")
                or function_args.get("raw_user_time_text")
            )
        )
    return has_datetime

def _extract_direct_submit_booking_args_from_user_message(
    text: str,
    *,
    phone: str | None,
    current_gender: str,
    fallback_name: str | None,
) -> dict[str, Any] | None:
    """Parse explicit technical booking fields from dashboard/admin test messages."""
    raw = text or ""
    low = raw.lower()
    if not any(tok in low for tok in ("احجز", "احجزي", "حجز", "book", "execute", "نفّذ", "نفذ")):
        return None

    def pick_int(field: str) -> int | None:
        m = re.search(rf"\b{re.escape(field)}\s*[:=]\s*(\d+)\b", raw, flags=re.IGNORECASE)
        return _safe_int(m.group(1)) if m else None

    sid = pick_int("service_id")
    bid = pick_int("branch_id")
    mid = pick_int("machine_id")

    bp_ids: list[int] = []
    m_bp = re.search(r"\bbody_part_ids\s*[:=]\s*\[([^\]]+)\]", raw, flags=re.IGNORECASE)
    if m_bp:
        bp_ids = _normalize_body_part_ids(m_bp.group(1))
    else:
        one_bp = pick_int("body_part_id")
        if one_bp is not None:
            bp_ids = [one_bp]

    m_dt = re.search(
        r"\b(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}:\d{2}(?::\d{2})?))?\b",
        raw,
    )
    if not m_dt:
        return None
    date_part = m_dt.group(1)
    time_part = m_dt.group(2)
    if not time_part:
        m_time = re.search(r"\b(\d{1,2}:\d{2})(?::\d{2})?\b", raw[m_dt.end() :])
        time_part = m_time.group(1) if m_time else None
    if not time_part:
        return None
    if len(time_part.split(":")) == 2:
        time_part = f"{time_part}:00"

    gender = current_gender if current_gender in ("male", "female") else None
    if any(tok in low for tok in ("نساء", "women", "female", "انثى", "أنثى", "بنت")):
        gender = "female"
    elif any(tok in low for tok in ("رجال", "men", "male", "ذكر", "شب")):
        gender = "male"

    out = {
        "intent": "create_appointment",
        "phone": phone or "",
        "service_id": sid,
        "branch_id": bid,
        "machine_id": mid if sid in LASER_HAIR_REMOVAL_SERVICE_IDS else None,
        "body_part_ids": bp_ids,
        "gender": gender,
        "customer_name": fallback_name,
        "normalized_date": date_part,
        "normalized_time": time_part[:5],
        "time": time_part[:5],
        "timezone": "Asia/Beirut",
        "date": f"{date_part} {time_part}",
        "execute_booking": True,
    }
    return out if _booking_submit_payload_complete_for_execution(out, gender or current_gender) else None

def _merge_explicit_user_booking_args(
    function_args: dict[str, Any],
    explicit_args: dict[str, Any] | None,
) -> bool:
    """Overlay explicit technical ids/date from the latest user message onto model tool args."""
    if not isinstance(function_args, dict) or not isinstance(explicit_args, dict):
        return False
    changed = False
    for key in (
        "service_id",
        "branch_id",
        "machine_id",
        "body_part_ids",
        "gender",
        "normalized_date",
        "normalized_time",
        "time",
        "timezone",
        "date",
        "execute_booking",
    ):
        val = explicit_args.get(key)
        if val is None or val == "" or val == []:
            continue
        if function_args.get(key) != val:
            function_args[key] = val
            changed = True
    if explicit_args.get("phone") and not function_args.get("phone"):
        function_args["phone"] = explicit_args["phone"]
        changed = True
    if explicit_args.get("customer_name") and not function_args.get("customer_name"):
        function_args["customer_name"] = explicit_args["customer_name"]
        changed = True
    if changed:
        function_args.pop("date_components", None)
        function_args.pop("calendar_day_intent", None)
    return changed

