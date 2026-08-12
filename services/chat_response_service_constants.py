"""Chat response constants (legacy GPT path)."""

from __future__ import annotations

from typing import Any

from utils.datetime_utils import (
    BOT_FIXED_TZ,
)

BOOKING_TZ = BOT_FIXED_TZ

ORCHESTRATION_MODEL = "gpt-5.1"

FINAL_RESPONSE_MODEL = "gpt-5.4-mini"

_TOOL_ROUND_ARGS_MAX = 48_000

_TOOL_ROUND_RESPONSE_MAX = 48_000

_custom_qa_cache: dict[str, Any] = {}

PRICE_STRONG_KEYWORDS = [
    "price",
    "cost",
    "how much",
    "pricing",
    "سعر",
    "اسعار",
    "تكلفة",
    "prix",
    "coût",
    "combien",
    "tarif",
    "sa3er",
]

PRICE_WEAK_KEYWORDS = [
    "كم",
    "قديش",
    "أديش",
    "adesh",
    "adde",
    "2adde",
    "2adesh",
    "kam",
]

_EXCLUDED_RESCHEDULE_SUMMARY_STATUSES = frozenset(
    {"done", "completed", "cancelled", "canceled", "missed", "no_show", "noshow"}
)

_PAUSED_LIKE_STATUS_NORMALIZED = frozenset(
    {
        "pause",
        "paused",
        "postpone",
        "postponed",
        "on hold",
        "hold",
        "paused appointment",
        "مؤجل",
        "مؤجل",
        "تاجيل",
        "تأجيل",
    }
)

CLINIC_PRICE_CONTEXT_KEYWORDS = [
    "laser",
    "ليزر",
    "جلسة",
    "جلسات",
    "service",
    "services",
    "خدمة",
    "خدمات",
    "appointment",
    "appointments",
    "موعد",
    "مواعيد",
    "booking",
    "حجز",
    "tattoo",
    "تاتو",
    "وشم",
    "dpl",
    "co2",
    "scar",
    "ندبة",
    "stretch",
    "hair",
    "شعر",
    "ليناز",
    "linas",
    "clinic",
    "عيادة",
]

OFF_TOPIC_PRICE_FALSE_POSITIVE_HINTS = [
    "president",
    "prime minister",
    "government",
    "politics",
    "country",
    "countries",
    "capital",
    "news",
    "weather",
    "bitcoin",
    "crypto",
    "دولة",
    "دول",
    "عالم",
    "رئيس",
    "سياسة",
    "طقس",
    "dawle",
    "dawlat",
    "3alam",
    "ra2is",
    "siyase",
    "siyaseh",
    "wazir",
    "ekhtara3",
    "e5tr3",
    "invented",
]

DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS = {1, 2, 4, 5, 11, 12, 13, 14}

LASER_HAIR_REMOVAL_SERVICE_IDS = {1, 12}

HAIR_REMOVAL_MACHINE_IDS = frozenset({9, 13, 15})

_SUBMIT_BOOKING_TOOL_HINT_TECHNICAL = (
    "A temporary technical error occurred while contacting the booking system. "
    "Do NOT show stack traces, exception text, HTTP bodies, or internal codes to the user. "
    "Reply in the user's language in one short message: apologize briefly, say the booking could not "
    "be completed right now, and ask whether they prefer another day or another time (or to try again shortly). "
    "Do not claim the appointment was booked."
)

_SUBMIT_BOOKING_TOOL_HINT_CRM_REJECT = (
    "The clinic calendar did not confirm this exact slot (it may be unavailable or blocked). "
    "Do NOT paste raw API messages, JSON, or field names to the user. "
    "Reply in the user's language in one short message: apologize softly and ask them to choose "
    "another day or another time. When they answer, call submit_booking_intent again with the updated choice. "
    "Do not claim the appointment was booked."
)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        return float(value)

    cleaned = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _normalize_body_part_ids(raw_value: Any) -> list[int]:
    if raw_value is None or raw_value == "":
        return []

    if isinstance(raw_value, list):
        result = []
        for item in raw_value:
            if item is None:
                continue
            if isinstance(item, dict):
                iid = _safe_int(item.get("body_part_id") or item.get("id"))
                if iid is not None and iid > 0:
                    result.append(iid)
                continue
            parsed = _safe_int(item)
            if parsed is not None and parsed > 0:
                result.append(parsed)
        return result

    if isinstance(raw_value, str):
        pieces = [part.strip() for part in raw_value.split(",") if part.strip()]
        result = []
        for part in pieces:
            parsed = _safe_int(part)
            if parsed is not None and parsed > 0:
                result.append(parsed)
        return result

    parsed_single = _safe_int(raw_value)
    return [parsed_single] if parsed_single is not None and parsed_single > 0 else []
