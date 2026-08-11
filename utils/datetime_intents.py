"""Multilingual datetime/appointment intent patterns and detectors."""

from __future__ import annotations

import re

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
    # Franco often writes "the day" as two words: "el yom" / "l yom" — was missing and broke
    # detect_day_reference vs stale "bokra" in the same concatenated user buffer.
    r"\bel\s+yom\b",
    r"\bl\s+yom\b",
    r"\b7al\s+yom\b",
    r"\bal\s+yom\b",
    r"\b3al\s+yom\b",
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

_RESCHEDULE_INTENT_PATTERNS = [
    # English
    r"\bpostpone\b",
    r"\breschedul(?:e|ing|ed)?\b",
    r"\bmove(?:\s+up)?\s+(?:my\s+)?appointment\b",
    r"\bchange\s+(?:my\s+)?appointment\b",
    r"\bshift\s+(?:my\s+)?appointment\b",
    r"\b(?:resume|reactivate|bring\s+back|continue)\b.{0,30}\b(?:appointment|appt|slot)\b",
    # Arabic
    r"(?:بدي|بدّي|ممكن|اريد|أريد|حابب|حابة)?\s*(?:أج[ّ]?ل|اج[ّ]?ل|تأجيل|تاجيل|أخ[ّ]?ر|اخر|غي[ّ]?ر|غير|عد[ّ]?ل|عدل|نق[ّ]?ل|نقل)\s*(?:لي)?\s*(?:موعدي|الموعد|موعد)",
    r"(?:موعدي|الموعد|موعد)\s*(?:بدي|بدّي|ممكن|اريد|أريد)?\s*(?:أج[ّ]?ل|اج[ّ]?ل|تأجيل|تاجيل|تعديل|تغيير|تأخير|تاخير|نقل)",
    r"(?:تأجيل|تاجيل|تغيير\s*الموعد|تبديل\s*الموعد|نقل\s*الموعد|موعد\s*تاني|موعد\s*اخر|موعد\s*آخر)",
    r"(?:رج[ّ]?ع|ارجع|يرجع|كم[ّ]?ل|كمل|فك|شيل).{0,35}(?:الموعد|موعدي|موعد|الموقوف|موقوف|البوز)",
    r"(?:رج[ّ]?ع|ارجع|يرجع).{0,12}(?:يجي|جي).{0,24}(?:على|ع)\s*(?:الموعد|موعدي|موعد)",
    # Franco-Arabic
    r"\b(a2?aj+el|ajjel|ta2?jil|2ajel|akher|ghayy?er|8ayyer|baddel|na2?el)\b.*\b(maw3ad|m3ad|mo3ad|mou3ad|appointment)\b",
    r"\b(rj+3|rje3|rja3|rod|rudd|kamm?el|kmel|fokk|fok|shil)\b.{0,30}\b(mw3ad|maw3ad|mou3ad|boz|pause|paused)\b",
    r"\b(rj+3|rje3|rja3)\b.{0,10}\b(yje|yeje|iji|yiji|ji)\b.{0,20}\b(3a|3al|aal|al)\b.{0,8}\b(mw3ad|maw3ad|mou3ad)\b",
    # French
    r"\b(reporter|reprogrammer|replanifier|d[ée]caler|changer)\b.*\b(rendez[- ]?vous)\b",
]

# User wants to edit an existing appointment without re-running a full new-booking flow
# (change machine/body areas/service/branch on a booked row).
_EXISTING_APPOINTMENT_EDIT_INTENT_PATTERNS = [
    # English
    r"\b(?:change|update|edit|switch|replace|add|remove)\b.*\b(?:machine|device|body\s*part|body\s*parts|area|areas|service|branch)\b.*\b(?:appointment|appt)\b",
    r"\b(?:appointment|appt)\b.*\b(?:change|update|edit|switch|replace|add|remove)\b.*\b(?:machine|device|body\s*part|body\s*parts|area|areas|service|branch)\b",
    # Arabic
    r"(?:موعدي|الموعد|موعد)\s*(?:بد[ّي]|\s*)?(?:غي[ّ]?ر|بد[ّ]?ل|عد[ّ]?ل|ض[يّ]?ف|ز[يي]د|شيل|احذف|بدّي\s*غي[ّ]?ر|بدّي\s*ض[يّ]?ف|بدّي\s*شيل).{0,40}(?:جهاز|الماكينة|المكنة|ماكنة|منطقة|مناطق|الخدمة|الفرع|body\s*part)",
    r"(?:غي[ّ]?ر|بد[ّ]?ل|عد[ّ]?ل|ض[يّ]?ف|ز[يي]د|شيل|احذف).{0,40}(?:جهاز|الماكينة|المكنة|ماكنة|منطقة|مناطق|الخدمة|الفرع|body\s*part).{0,30}(?:موعدي|الموعد|موعد)",
    # Franco-Arabic
    r"\b(?:ghayy?er|8ayyer|baddel|3addel|adel|zid|zeed|deef|dif|add|remove|shil)\b.{0,40}\b(?:machine|device|makina|mkene|mekne|body\s*part|body\s*parts|area|areas|service|branch|manati2|manta2a)\b.{0,30}\b(?:maw3ad|mw3ad|mou3ad|appointment)\b",
    r"\b(?:maw3ad|mw3ad|mou3ad|appointment)\b.{0,30}\b(?:ghayy?er|8ayyer|baddel|3addel|adel|zid|zeed|deef|dif|add|remove|shil)\b.{0,40}\b(?:machine|device|makina|mkene|mekne|body\s*part|body\s*parts|area|areas|service|branch|manati2|manta2a)\b",
    # French
    r"\b(?:changer|modifier|ajouter|retirer|enlever)\b.*\b(?:machine|appareil|zone|zones|service|branche)\b.*\b(?:rendez[- ]?vous)\b",
    r"\b(?:rendez[- ]?vous)\b.*\b(?:changer|modifier|ajouter|retirer|enlever)\b.*\b(?:machine|appareil|zone|zones|service|branche)\b",
]

# User wants to *see* appointment(s): when, what is booked, list paused, etc. (not necessarily reschedule).
_APPOINTMENT_INQUIRY_INTENT_PATTERNS = [
    # Franco: emtan/2mtan/mtan + mw3ad / mw3de / maw3ad…
    r"\b(?:e|i)?mtan\s+mw3",
    r"\b2mtan\s+mw3",
    r"\bmtan\s+mw3",
    r"\bemtan\s+mou?3",
    r"\bmw3(?:ad|de)\s+ana\b",
    r"\bmaw3ad\s+ana\b",
    r"\bmou3ad\s+ana\b",
    # Arabic
    r"(?:شو|إمتى|امتى|متى|وين)\s*(?:هو\s*)?موعدي",
    r"موعدي\s*(?:شو|إمتى|امتى|متى|وين|ايمتا)",
    r"\bاعرف\s+موعدي\b",
    r"\ba3ref\s+mw3ad\b",
    r"\b(?:شو\s+هي|شو\s+هني)\s+المواعيد",
    r"\bشو\s+ه(?:ني|ي)\s+el\s+mw3",
    # English
    r"\bwhen\s+is\s+my\s+appointment\b",
    r"\bwhat(?:'s|s| is)\s+my\s+appointment\b",
    r"\bmy\s+appointment\s+(?:when|what|time)\b",
    # How many / list paused
    r"\bkam\s+mw3ad\b",
    r"\bkam\s+maw3ad\b",
    r"\bmw3(?:ad|id|ed)\s+el\s+wa2?f",
    r"\bmo?wa2?f(?:een|in|e)?\b.*\b(mw3|maw3|mou3|appointment)\b",
    r"\b(mw3|maw3|mou3|appointment)\b.*\bmo?wa2?f(?:een|in|e)?\b",
    # French
    r"\bmon\s+rendez[- ]?vous\b",
    r"\bquand\s+est\s+(?:mon\s+)?rendez[- ]?vous\b",
]

# User wants every listed / paused row moved to the same new slot (Franco + Arabic).
_BULK_RESCHEDULE_ALL_PATTERNS = [
    r"\b3m(?:el|al|le)(?:on|eon|en)?\s+kelon\b",
    r"\b3ml(?:on|eon|en)\s+kelon\b",
    r"\b(?:7ot|hot)(?:le|li)?\s+hene\s+kelon\b",
    r"\bhene\s+kelon\b",
    r"\bkelon\b.*\b(bokra|bukra|bekra|tomorrow)\b",
    r"\b(bokra|bukra)\b.*\bkelon\b",
    r"\ball\s+of\s+them\b",
    r"\bmove\s+all\b",
    r"\breschedul(?:e|ing)?\s+all\b",
]

# Levantine / Franco weekday hints for reschedule threads (Monday=0 .. Sunday=6, Python weekday).
_WEEKDAY_INTENT_PATTERNS: list[tuple[int, re.Pattern]] = [
    (0, re.compile(r"\b(tanen|tnen|tnine|monday|الاثنين|اثنين)\b", re.I)),
    (
        1,
        re.compile(
            r"\b(talta|tlata|tlate|tuesday|الثلاثاء|ثلاثاء|نهار\s+ال(?:تلاتا|تلاثا|ثلاثا))\b",
            re.I,
        ),
    ),
    (
        2,
        re.compile(
            r"\b(arbaa|arbe3|arbe2|arb3a|wednesday|الاربعاء|الأربعاء|اربعاء|نهار\s+الاربعا)\b",
            re.I,
        ),
    ),
    (
        3,
        re.compile(
            r"\b(khamis|5amis|5ames|5amess|thursday|الخميس|خميس|نهار\s+الخميس)\b",
            re.I,
        ),
    ),
    (4, re.compile(r"\b(jom3a|jum3a|jem3a|friday|الجمعة|جمعة)\b", re.I)),
    (5, re.compile(r"\b(sabt|sbt|saturday|السبت|سبت)\b", re.I)),
    (6, re.compile(r"\b(ahad|7ad|had|sunday|الاحد|الأحد|احد)\b", re.I)),
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_appointment_inquiry_intent(text: str) -> bool:
    """True when the user asks to see / list / when their appointment(s) are (incl. paused)."""
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _APPOINTMENT_INQUIRY_INTENT_PATTERNS)


def detect_bulk_reschedule_all_intent(text: str) -> bool:
    """True when the user asks to apply the same change to every appointment row (e.g. all paused → tomorrow)."""
    raw = (text or "").strip()
    if not raw:
        return False
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if any(x in raw for x in ("كلهم", "كلون", "كل المواعيد", "كل مواعيدي")):
        return True
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _BULK_RESCHEDULE_ALL_PATTERNS)


def detect_existing_appointment_edit_intent(text: str) -> bool:
    """True when the user wants to edit machine/body parts/service/branch on an existing appointment."""
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(
        re.search(pattern, normalized, re.IGNORECASE | re.UNICODE)
        for pattern in _EXISTING_APPOINTMENT_EDIT_INTENT_PATTERNS
    )


def detect_relative_intent(text: str) -> str | None:
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


def detect_day_reference(text: str) -> str | None:
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


def detect_reschedule_intent(text: str) -> bool:
    """Return True when text clearly asks to postpone/reschedule an appointment."""
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _RESCHEDULE_INTENT_PATTERNS)


def detect_last_weekday_intent_from_user_text(text: str) -> int | None:
    """
    Return the weekday (0=Mon .. 6=Sun) of the **last** weekday phrase in user-authored text.
    Used when the model sends the wrong calendar day but the customer already named a target day
    (e.g. «نهار التلاتا») and then only sends an appointment_id.
    """
    if not text or not str(text).strip():
        return None
    best_end = -1
    best_wd: int | None = None
    for wd, rx in _WEEKDAY_INTENT_PATTERNS:
        for m in rx.finditer(text):
            if m.end() > best_end:
                best_end = m.end()
                best_wd = wd
    return best_wd
