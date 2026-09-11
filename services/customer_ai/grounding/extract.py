"""Surface extractors for grounding checks. Pure regex, no LLM and no network.

Every extractor runs the same way over the reply and over the evidence corpus, so a
claim counts as grounded only when the identical normalized surface exists in evidence.
"""

from __future__ import annotations

import re

from services.customer_ai.normalize import normalize_search_text

_SPACE = re.compile(r"\s+")
_AMOUNT_SUFFIX = re.compile(r"(\d+(?:[.,]\d+)?)\s*(usd|lbp|eur|gbp|\$|€)", re.I)
_AMOUNT_PREFIX = re.compile(r"(usd|lbp|eur|gbp|\$|€)\s*(\d+(?:[.,]\d+)?)", re.I)
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?", re.I)
_HOUR_MERIDIEM = re.compile(r"\b(\d{1,2})\s*(am|pm)\b", re.I)
_PHONE = re.compile(r"\+?\d[\d\s\-().]{5,}\d")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.I)
_DIGITS = re.compile(r"\D+")

_CURRENCY_ALIAS = {"$": "usd", "€": "eur"}

# Reply surfaces that assert opening hours. Presence forces a time/day evidence check.
OPEN_MARKERS: tuple[str, ...] = (
    "open until",
    "open till",
    "open from",
    "opens at",
    "closes at",
    "closing at",
    "closed on",
    "open on",
    "we are open",
    "we re open",
    "were open",
    "opening hours",
    "working hours",
    "business hours",
    "ساعات العمل",
    "ساعات الدوام",
    "مفتوحين",
    "مفتوح",
    "بنفتح",
    "بنسكر",
)

# Day surfaces map to one canonical day so an Arabic reply about English evidence (and the
# reverse) is compared by day, not by spelling.
DAY_ALIASES: dict[str, str] = {
    "monday": "monday",
    "mon": "monday",
    "الاثنين": "monday",
    "الاتنين": "monday",
    "tuesday": "tuesday",
    "tue": "tuesday",
    "الثلاثاء": "tuesday",
    "الثلاثا": "tuesday",
    "wednesday": "wednesday",
    "wed": "wednesday",
    "الاربعاء": "wednesday",
    "الاربعا": "wednesday",
    "thursday": "thursday",
    "thu": "thursday",
    "الخميس": "thursday",
    "friday": "friday",
    "fri": "friday",
    "الجمعه": "friday",
    "saturday": "saturday",
    "sat": "saturday",
    "السبت": "saturday",
    "sunday": "sunday",
    "sun": "sunday",
    "الاحد": "sunday",
}

STOCK_CLAIMS: tuple[str, ...] = (
    "in stock",
    "out of stock",
    "back in stock",
    "available now",
    "sold out",
    "we have it available",
    "متوفر",
    "غير متوفر",
    "موجود بالمخزن",
)

STOCK_SUPPORT: tuple[str, ...] = (
    "stock",
    "availability",
    "available",
    "unavailable",
    "inventory",
    "quantity",
    "qty",
    "sold out",
    "متوفر",
    "الكميه",
    "المخزن",
)

BOOKING_CLAIMS: tuple[str, ...] = (
    "booked",
    "booking is confirmed",
    "booking confirmed",
    "appointment is confirmed",
    "appointment confirmed",
    "confirmed your appointment",
    "confirmed your booking",
    "reservation confirmed",
    "reserved your",
    "you are all set",
    "you re all set",
    "youre all set",
    "تم الحجز",
    "تم تثبيت",
    "حجزتلك",
    "محجوز",
)

RECEIPT_SUCCESS: tuple[str, ...] = (
    "succeeded",
    "success",
    "confirmed",
    "created",
    "booked",
    "completed",
    "reserved",
    "scheduled",
)


def flat(text: str) -> str:
    """Casefold and collapse whitespace, keeping punctuation (times, urls, phones)."""
    return _SPACE.sub(" ", (text or "").casefold()).strip()


def marker_text(text: str) -> str:
    """Punctuation-free, Arabic-normalized surface for phrase markers."""
    return normalize_search_text(text)


def has_marker(normalized: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        if marker.isascii():
            if re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", normalized):
                return marker
        elif marker in normalized:
            return marker
    return ""


def _number(raw: str) -> str:
    cleaned = raw.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return raw
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _currency(raw: str) -> str:
    token = raw.strip().casefold()
    return _CURRENCY_ALIAS.get(token, token)


def amounts(text: str) -> set[str]:
    """Money surfaces as `<number>|<currency>`, e.g. `250|usd`."""
    found: set[str] = set()
    for match in _AMOUNT_SUFFIX.finditer(text or ""):
        found.add(f"{_number(match.group(1))}|{_currency(match.group(2))}")
    for match in _AMOUNT_PREFIX.finditer(text or ""):
        found.add(f"{_number(match.group(2))}|{_currency(match.group(1))}")
    return found


def _clock_variants(hour: int, minute: int) -> frozenset[str]:
    """12h/24h forms of one clock time; evidence expands the same way."""
    normalized = hour % 24
    forms = {f"{normalized:02d}:{minute:02d}"}
    twin = normalized + 12 if normalized < 12 else normalized - 12
    forms.add(f"{twin:02d}:{minute:02d}")
    return frozenset(forms)


def clock_claims(text: str) -> list[frozenset[str]]:
    """Every clock time in the text, each as its set of equivalent surfaces."""
    out: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    body = flat(text)
    for match in _CLOCK.finditer(body):
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 24 or minute > 59:
            continue
        meridiem = (match.group(3) or "").casefold()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        variants = _clock_variants(hour, minute)
        if variants not in seen:
            seen.add(variants)
            out.append(variants)
    for match in _HOUR_MERIDIEM.finditer(body):
        hour = int(match.group(1))
        if hour > 12:
            continue
        if match.group(2).casefold() == "pm" and hour < 12:
            hour += 12
        elif match.group(2).casefold() == "am" and hour == 12:
            hour = 0
        variants = _clock_variants(hour, 0)
        if variants not in seen:
            seen.add(variants)
            out.append(variants)
    return out


def clock_surfaces(text: str) -> set[str]:
    surfaces: set[str] = set()
    for variants in clock_claims(text):
        surfaces |= set(variants)
    return surfaces


def days(text: str) -> set[str]:
    """Canonical day names claimed by the text, in any supported spelling."""
    normalized = marker_text(text)
    return {canonical for alias, canonical in DAY_ALIASES.items() if has_marker(normalized, (alias,))}


def phones(text: str) -> set[str]:
    """Digit-only phone surfaces, 7..15 digits. Clock times are removed first."""
    found: set[str] = set()
    body = _CLOCK.sub(" ", text or "")
    for match in _PHONE.finditer(body):
        digits = _DIGITS.sub("", match.group(0))
        if 7 <= len(digits) <= 15:
            found.add(digits)
    return found


def phone_grounded(claimed: str, allowed: set[str]) -> bool:
    """Local vs international forms of the same number count as one number."""
    tail = claimed[-7:]
    for candidate in allowed:
        if candidate.endswith(tail) or claimed.endswith(candidate[-7:]):
            return True
    return False


def urls(text: str) -> set[str]:
    found: set[str] = set()
    for match in _URL.finditer(text or ""):
        raw = match.group(0).casefold().rstrip(".,;:!?)]}\"'")
        raw = re.sub(r"^https?://", "", raw)
        raw = raw.removeprefix("www.").rstrip("/")
        if raw:
            found.add(raw)
    return found
