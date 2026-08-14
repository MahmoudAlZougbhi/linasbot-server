"""Per-customer AI limits: word truncation, reply/photo/voice caps, period reset."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.ai_limits_enforcement import apply_inbound_word_limit, enforce_text_reply_quota
from services.ai_limits_source import section_to_enforcement_updates, sync_enforcement_from_payload
from services.ai_usage_limits import AiUsageLimitsService, month_period_key
from services.ai_usage_limits_settings import (
    day_period_key,
    period_reset_at,
    truncate_text_to_words,
    week_period_key,
)
from services.cm.schemas import AiLimitsSection


@pytest.fixture()
def limits_svc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AiUsageLimitsService:
    svc = AiUsageLimitsService(store_dir=tmp_path / "ai_limits")
    monkeypatch.setattr("services.ai_usage_limits.ai_usage_limits_service", svc)
    monkeypatch.setattr("services.ai_limits_enforcement.ai_usage_limits_service", svc)
    monkeypatch.setattr("services.ai_limits_source.ai_usage_limits_service", svc)
    return svc


def test_inbound_over_limit_is_truncated_to_configured_words(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings("clinic-a", {"text_words_per_message": 3})
    user = {"tenant_id": "clinic-a", "social_sender_id": "wa:1"}
    text = "one two three four five six"
    clipped, notice = apply_inbound_word_limit(user_id="wa:1", user_data=user, text=text)
    assert clipped == "one two three"
    assert notice
    assert "3" in notice
    assert truncate_text_to_words(text, 3).split() == ["one", "two", "three"]


def test_reply_quota_blocks_over_limit_inbound(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings(
        "clinic-a",
        {"text_replies_per_day": 2, "text_replies_per_week": 10, "text_replies_per_month": 20},
    )
    user = {"tenant_id": "clinic-a", "social_sender_id": "ig:1", "user_preferred_lang": "en"}
    first = enforce_text_reply_quota(user_id="ig:1", user_data=user, consume=True)
    second = enforce_text_reply_quota(user_id="ig:1", user_data=user, consume=True)
    third = enforce_text_reply_quota(user_id="ig:1", user_data=user, consume=True)
    assert first.allowed and second.allowed
    assert not third.allowed
    assert third.reason == "reply_day_limit"
    assert third.reset_at
    assert "daily" in (third.customer_message or "")
    other = enforce_text_reply_quota(
        user_id="ig:2",
        user_data={"tenant_id": "clinic-a", "social_sender_id": "ig:2"},
        consume=True,
    )
    assert other.allowed


def test_photo_month_cap_and_per_message(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings(
        "clinic-a",
        {"photos_per_message": 2, "image_per_day": 10, "image_per_week": 20, "image_per_month": 3},
    )
    d1 = limits_svc.consume_images("clinic-a", "u1", amount=5)
    assert d1.allowed
    assert d1.allowed_amount == 2
    d2 = limits_svc.consume_images("clinic-a", "u1", amount=2)
    assert d2.allowed_amount == 1
    d3 = limits_svc.consume_images("clinic-a", "u1", amount=1)
    assert not d3.allowed
    assert d3.reason == "image_month_limit"


def test_voice_minutes_cap(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings(
        "clinic-a",
        {
            "voice_minutes_per_message": 2,
            "voice_minutes_per_day": 3,
            "voice_minutes_per_week": 10,
            "voice_minutes_per_month": 20,
        },
    )
    first = limits_svc.consume_voice_minutes("clinic-a", "u1", amount=5)
    assert first.allowed_amount == 2
    second = limits_svc.consume_voice_minutes("clinic-a", "u1", amount=2)
    assert second.allowed_amount == 1
    third = limits_svc.consume_voice_minutes("clinic-a", "u1", amount=1)
    assert not third.allowed
    assert third.reason == "voice_day_limit"


def test_period_window_auto_resets(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings("clinic-a", {"text_replies_per_day": 1, "text_replies_per_week": 10, "text_replies_per_month": 30})
    day = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    first = limits_svc.consume_replies("clinic-a", "u1", amount=1, now=day)
    blocked = limits_svc.consume_replies("clinic-a", "u1", amount=1, now=day)
    assert first.allowed
    assert not blocked.allowed
    next_day = day + timedelta(days=1)
    assert day_period_key(next_day) != day_period_key(day)
    assert week_period_key(day).startswith("week:")
    assert month_period_key(day).startswith("month:")
    reset = limits_svc.consume_replies("clinic-a", "u1", amount=1, now=next_day)
    assert reset.allowed
    assert period_reset_at("day", day) == datetime(2026, 8, 16, tzinfo=UTC)


def test_cm_section_syncs_new_knobs_into_enforcement(limits_svc: AiUsageLimitsService) -> None:
    section = AiLimitsSection(
        unlimited=True,
        text_words_per_message=40,
        text_replies_per_day=4,
        photos_per_message=1,
        voice_minutes_per_day=7,
    )
    sync_enforcement_from_payload("clinic-a", section.model_dump(mode="json"))
    settings = limits_svc.get_settings("clinic-a")
    assert settings.text_words_per_message == 40
    assert settings.text_replies_per_day == 4
    assert settings.photos_per_message == 1
    assert settings.voice_minutes_per_day == 7
    dumped = section_to_enforcement_updates(section)
    assert "text_replies_per_month" in dumped
    assert dumped["unlimited"] is False
    assert "TikTok" not in str(dumped)
