import datetime

import pytest

from utils.datetime_utils import (
    BOT_FIXED_TZ,
    align_datetime_to_day_reference,
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


def test_align_today_reference_when_candidate_is_tomorrow():
    candidate = datetime.datetime(2026, 2, 28, 15, 0, 0, tzinfo=BOT_FIXED_TZ)
    aligned = align_datetime_to_day_reference(candidate, "later today", reference=REFERENCE_NOW)
    assert aligned.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-27 15:00:00"


def test_align_tomorrow_reference_when_candidate_is_today():
    candidate = datetime.datetime(2026, 2, 27, 9, 0, 0, tzinfo=BOT_FIXED_TZ)
    aligned = align_datetime_to_day_reference(candidate, "بكرا", reference=REFERENCE_NOW)
    assert aligned.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-28 09:00:00"
