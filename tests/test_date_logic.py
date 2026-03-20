import datetime

import pytest

from utils.datetime_utils import (
    BOT_FIXED_TZ,
    align_datetime_to_day_reference,
    datetime_from_ai_date_components,
    detect_appointment_inquiry_intent,
    detect_bulk_reschedule_all_intent,
    detect_day_reference,
    detect_relative_intent,
    detect_reschedule_intent,
    format_clinic_calendar_anchor,
    parse_datetime_flexible,
    resolve_relative_datetime,
    text_mentions_datetime,
)


REFERENCE_NOW = datetime.datetime(2026, 2, 27, 10, 0, 0, tzinfo=BOT_FIXED_TZ)


@pytest.mark.parametrize(
    "text",
    [
        "اليوم الساعة 3",
        "بكرا الصبح",
        "بكرة الصبح",
        "later today",
        "tomorrow morning",
        "بعد ساعتين",
        "demain matin",
        "bukra el soboh",
    ],
)
def test_text_mentions_datetime_multilingual(text):
    assert text_mentions_datetime(text) is True


def test_parse_datetime_with_timezone_offset_to_plus0200():
    parsed = parse_datetime_flexible("2026-02-27T23:30:00+00:00")
    assert parsed is not None
    assert parsed.tzinfo == BOT_FIXED_TZ
    assert parsed.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-28 01:30:00"


def test_resolve_relative_after_two_hours_arabic():
    resolved = resolve_relative_datetime("بعد ساعتين", reference=REFERENCE_NOW)
    assert resolved is not None
    assert resolved.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-27 12:00:00"


@pytest.mark.parametrize(
    "text",
    ["tomorrow morning", "بكرا الصبح", "demain matin", "bokra sob7"],
)
def test_resolve_relative_tomorrow_morning(text):
    resolved = resolve_relative_datetime(text, reference=REFERENCE_NOW)
    assert resolved is not None
    assert resolved.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-28 10:00:00"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("اليوم", "today"),
        ("بكرا", "tomorrow"),
        ("today", "today"),
        ("tomorrow", "tomorrow"),
        ("بكرا الصبح", "tomorrow"),
        ("بكرة الصبح", "tomorrow"),
    ],
)
def test_detect_day_reference_core_keywords(text, expected):
    assert detect_day_reference(text) == expected


def test_detect_relative_intent_core_phrases():
    assert detect_relative_intent("بعد ساعتين") == "after_two_hours"
    assert detect_relative_intent("later today") == "later_today"
    assert detect_relative_intent("tomorrow morning") == "tomorrow_morning"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tomorrow at 5 no later today", "today"),
        ("later today no tomorrow morning", "tomorrow"),
        ("بكرا الساعة 5 لا اليوم", "today"),
        ("اليوم الساعة 5 لا بكرا الصبح", "tomorrow"),
    ],
)
def test_detect_day_reference_prefers_latest_mention(text, expected):
    assert detect_day_reference(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hotle mw3ad el yom", "today"),
        ("hote mw3ad el yom se3a 1", "today"),
        ("mw3ad el yom", "today"),
        ("7al yom", "today"),
        ("bokra ok el yom", "today"),
    ],
)
def test_detect_day_reference_franco_el_yom(text, expected):
    assert detect_day_reference(text) == expected


def test_resolve_relative_franco_el_yom_today():
    resolved = resolve_relative_datetime("hotle mw3ad el yom se3a 1", reference=REFERENCE_NOW)
    assert resolved is not None
    # 01:00 is before reference 10:00 → bumped to now + 30m same day
    assert resolved.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-27 10:30:00"


def test_resolve_relative_bokra_tomorrow():
    resolved = resolve_relative_datetime("bokra se3a 3", reference=REFERENCE_NOW)
    assert resolved is not None
    assert resolved.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-28 03:00:00"


def test_forced_day_ref_overrides_stale_bokra_in_buffer():
    """Latest message says today; older 'bokra' in same buffer must not win."""
    buf = "bokra " * 8 + "hotle mw3ad el yom se3a 2"
    assert detect_day_reference(buf) == "today"
    latest = "hotle mw3ad el yom se3a 2"
    resolved = resolve_relative_datetime(
        buf, reference=REFERENCE_NOW, forced_day_ref=detect_day_reference(latest)
    )
    assert resolved.date() == REFERENCE_NOW.date()
    # 02:00 same day is before reference 10:00 → bump to 10:30
    assert resolved.strftime("%H:%M:%S") == "10:30:00"


def test_format_clinic_calendar_anchor_contains_isos():
    s = format_clinic_calendar_anchor(REFERENCE_NOW)
    assert "2026-02-27" in s and "2026-02-28" in s


def test_datetime_from_ai_date_components_ok():
    dt = datetime_from_ai_date_components({"year": 2026, "month": 3, "day": 21, "hour": 13, "minute": 0})
    assert dt is not None
    assert dt.tzinfo == BOT_FIXED_TZ
    assert dt.strftime("%Y-%m-%d %H:%M:%S") == "2026-03-21 13:00:00"


def test_datetime_from_ai_date_components_invalid():
    assert datetime_from_ai_date_components(None) is None
    assert datetime_from_ai_date_components({"year": 2026, "month": 2, "day": 31, "hour": 10}) is None
    assert datetime_from_ai_date_components({"year": 2026, "month": 3, "day": 1}) is None


def test_align_today_reference_when_candidate_is_tomorrow():
    candidate = datetime.datetime(2026, 2, 28, 15, 0, 0, tzinfo=BOT_FIXED_TZ)
    aligned = align_datetime_to_day_reference(candidate, "later today", reference=REFERENCE_NOW)
    assert aligned.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-27 15:00:00"


def test_align_tomorrow_reference_when_candidate_is_today():
    candidate = datetime.datetime(2026, 2, 27, 9, 0, 0, tzinfo=BOT_FIXED_TZ)
    aligned = align_datetime_to_day_reference(candidate, "بكرا", reference=REFERENCE_NOW)
    assert aligned.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-28 09:00:00"


@pytest.mark.parametrize(
    "text",
    [
        "postpone to today",
        "please reschedule my appointment",
        "بدي أجل موعدي لليوم",
        "ممكن تغيير الموعد",
        "je veux reporter mon rendez-vous",
    ],
)
def test_detect_reschedule_intent_multilingual_positive(text):
    assert detect_reschedule_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "what are your working hours today",
        "ما هي ساعات العمل اليوم؟",
        "hello",
        "كم سعر الجلسة؟",
    ],
)
def test_detect_reschedule_intent_negative(text):
    assert detect_reschedule_intent(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Emtan mw3de",
        "Kifak emtan mw3de ana",
        "emtan mw3ad ana",
        "2mtan mw3de",
        "when is my appointment",
        "kam mw3ad 3end mw2f le",
        "sho hene el mw3id el wa2fe",
        "موعدي إمتى",
        "quand est mon rendez-vous",
    ],
)
def test_detect_appointment_inquiry_intent_positive(text):
    assert detect_appointment_inquiry_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "postpone my appointment to tomorrow",
        "hello kifak",
        "book laser tomorrow",
    ],
)
def test_detect_appointment_inquiry_intent_negative(text):
    assert detect_appointment_inquiry_intent(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "3mlon kelon",
        "3mle hene kelon bokra 3al se3a 1",
        "kelon bokra",
        "bokra kelon",
        "hene kelon",
        "كلهم",
        "عدّل كل المواعيد",
        "move all to tomorrow",
        "reschedule all",
    ],
)
def test_detect_bulk_reschedule_all_intent_positive(text):
    assert detect_bulk_reschedule_all_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "بدي أجل موعد وحيد بكرا",
        "postpone one appointment",
        "kelon",  # alone, no day / no Arabic all-of-them
    ],
)
def test_detect_bulk_reschedule_all_intent_negative(text):
    assert detect_bulk_reschedule_all_intent(text) is False
