"""Date and time helpers for booking logic (fixed UTC+0200)."""

from __future__ import annotations

import datetime
import re
from typing import Optional


BOT_FIXED_TZ = datetime.timezone(datetime.timedelta(hours=2), name="+0200")


def now_in_bot_tz() -> datetime.datetime:
    """Return current aware datetime in fixed +0200 timezone."""
    return datetime.datetime.now(BOT_FIXED_TZ)


def to_bot_tz(dt: datetime.datetime) -> datetime.datetime:
    """Convert datetime to fixed +0200 timezone (assume +0200 if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BOT_FIXED_TZ)
    return dt.astimezone(BOT_FIXED_TZ)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


_AFTER_TWO_HOURS_PATTERNS = [
    r"\bafter\s+two\s+hours\b",
    r"\bafter\s+2\s+hours\b",
    r"\bin\s+two\s+hours\b",
    r"\bin\s+2\s+hours\b",
    r"\bبعد\s*ساعتين\b",
    r"\bخلال\s*ساعتين\b",
    r"\bba3d\s+sa3t(?:e|a){1,2}n\b",
    r"\bbaad\s+sa3t(?:e|a){1,2}n\b",
    r"\bdans\s+deux\s+heures\b",
    r"\bdans\s+2\s+heures\b",
]

_TOMORROW_MORNING_PATTERNS = [
    r"\btomorrow\s+morning\b",
    r"\bdemain\s+matin\b",
    r"\bبكرا\s*الصبح\b",
    r"\bبكر[اة]\s*الصبح\b",
    r"\bبكر[اة]\s*صبح(?:ا)?\b",
    r"\bغد[اًا]?\s*صباح(?:ا)?\b",
    r"\bb(?:u|o)kra\s+(?:el\s+)?(?:soboh|sobh|sob7|saba7)\b",
]

_LATER_TODAY_PATTERNS = [
    r"\blater\s+today\b",
    r"\btoday\s+later\b",
    r"\bthis\s+evening\b",
    r"\btonight\b",
    r"\bاليوم\s+(?:لاحق(?:ا)?|بعدين|المسا|بالليل)\b",
    r"\blyom\s+ba3den\b",
    r"\belyom\s+ba3den\b",
    r"\baujourd['’]hui\s+plus\s+tard\b",
    r"\bplus\s+tard\s+aujourd['’]hui\b",
    r"\bce\s+soir\b",
]

_TODAY_PATTERNS = [
    r"\btoday\b",
    r"\baujourd['’]hui\b",
    r"\bاليوم\b",
    r"\bهاليوم\b",
    r"\blyom\b",
    r"\belyom\b",
    r"\balyom\b",
]

_TOMORROW_PATTERNS = [
    r"\btomorrow\b",
    r"\bdemain\b",
    r"\bبكرا\b",
    r"\bبكر[اة]\b",
    r"\bغد[اًا]?\b",
    r"\bbukra\b",
    r"\bbokra\b",
    r"\bbekra\b",
]

_EXPLICIT_DATETIME_PATTERNS = [
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}\s*(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|صباحا|مساء|الصبح|بالليل|noon|midnight)\b",
    r"\b\d{1,2}:\d{2}\b",
    r"\bat\s+\d{1,2}(?::\d{2})?\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(?:الاثنين|الثلاثاء|الاربعاء|الخميس|الجمعة|السبت|الاحد)\b",
]


def detect_relative_intent(text: str) -> Optional[str]:
    """
    Detect explicit relative datetime intents from multilingual text.
    Returns one of: after_two_hours, tomorrow_morning, later_today, or None.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return None

    def _last_match_pos(patterns: list[str]) -> int:
        last_pos = -1
        for pattern in patterns:
            for match in re.finditer(pattern, normalized, re.IGNORECASE):
                last_pos = max(last_pos, match.start())
        return last_pos

    intent_positions = {
        "after_two_hours": _last_match_pos(_AFTER_TWO_HOURS_PATTERNS),
        "tomorrow_morning": _last_match_pos(_TOMORROW_MORNING_PATTERNS),
        "later_today": _last_match_pos(_LATER_TODAY_PATTERNS),
    }
    best_intent, best_pos = max(intent_positions.items(), key=lambda item: item[1])
    if best_pos != -1:
        return best_intent
    return None


def detect_day_reference(text: str) -> Optional[str]:
    """Return expected day bucket from text: 'today', 'tomorrow', or None."""
    normalized = _normalize_text(text)
    if not normalized:
        return None

    def _last_match_pos(patterns: list[str]) -> int:
        last_pos = -1
        for pattern in patterns:
            for match in re.finditer(pattern, normalized, re.IGNORECASE):
                last_pos = max(last_pos, match.start())
        return last_pos

    tomorrow_pos = max(
        _last_match_pos(_TOMORROW_MORNING_PATTERNS),
        _last_match_pos(_TOMORROW_PATTERNS),
    )
    today_pos = max(
        _last_match_pos(_LATER_TODAY_PATTERNS),
        _last_match_pos(_TODAY_PATTERNS),
    )

    if tomorrow_pos == -1 and today_pos == -1:
        return None
    if tomorrow_pos > today_pos:
        return "tomorrow"
    if today_pos > tomorrow_pos:
        return "today"

    # Tie-breaker: fall back to relative intent (more specific than day keyword).
    relative_intent = detect_relative_intent(normalized)
    if relative_intent == "tomorrow_morning":
        return "tomorrow"
    if relative_intent in {"after_two_hours", "later_today"}:
        return "today"

    # Stable fallback if both exist at the exact same position.
    return "today" if today_pos != -1 else "tomorrow"


def text_mentions_datetime(text: str) -> bool:
    """Return True if text contains any date/time hint in supported languages."""
    normalized = _normalize_text(text)
    if not normalized:
        return False

    if detect_relative_intent(normalized) or detect_day_reference(normalized):
        return True

    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _EXPLICIT_DATETIME_PATTERNS)


def parse_datetime_flexible(date_value: str) -> Optional[datetime.datetime]:
    """
    Parse flexible date strings into aware +0200 datetime.
    Supports common GPT outputs and ISO strings with timezone offsets.
    """
    if date_value is None:
        return None

    value = str(date_value).strip()
    if not value:
        return None

    # Handle ISO with "Z"
    iso_value = value.replace("Z", "+00:00")

    # Try ISO parser first (handles offsets)
    try:
        dt = datetime.datetime.fromisoformat(iso_value)
        dt = to_bot_tz(dt)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            dt = dt.replace(hour=10, minute=0, second=0, microsecond=0)
        return dt
    except ValueError:
        pass

    # Try explicit formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"):
        try:
            parsed = datetime.datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=BOT_FIXED_TZ, microsecond=0)
        except ValueError:
            continue

    # Date only
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.datetime.strptime(value, fmt)
            parsed = parsed.replace(hour=10, minute=0, second=0, microsecond=0)
            return parsed.replace(tzinfo=BOT_FIXED_TZ)
        except ValueError:
            continue

    return None


def resolve_relative_datetime(text: str, reference: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
    """Resolve supported relative phrases to a concrete +0200 datetime."""
    now = to_bot_tz(reference) if reference is not None else now_in_bot_tz()
    intent = detect_relative_intent(text)
    if not intent:
        return None

    if intent == "after_two_hours":
        return (now + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)

    if intent == "tomorrow_morning":
        return (now + datetime.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

    if intent == "later_today":
        candidate = (now + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)
        if candidate.date() != now.date():
            candidate = (now + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
        return candidate

    return None


def align_datetime_to_day_reference(
    candidate: datetime.datetime,
    text: str,
    reference: Optional[datetime.datetime] = None
) -> datetime.datetime:
    """
    Align a parsed datetime with user's day reference (today/tomorrow) when present.
    """
    now = to_bot_tz(reference) if reference is not None else now_in_bot_tz()
    dt = to_bot_tz(candidate)
    day_ref = detect_day_reference(text)
    if not day_ref:
        return dt

    if day_ref == "today" and dt.date() != now.date():
        dt = dt.replace(year=now.year, month=now.month, day=now.day)
    elif day_ref == "tomorrow":
        tomorrow = (now + datetime.timedelta(days=1)).date()
        if dt.date() != tomorrow:
            dt = dt.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)

    return dt
