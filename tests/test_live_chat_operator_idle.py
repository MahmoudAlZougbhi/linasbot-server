"""Idle operator view must resume AI; an open thread must keep AI paused."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from services.live_chat_contracts import UTC
from services.live_chat_operator_idle import (
    OPERATOR_IDLE_RESUME_SECONDS,
    auto_resume_if_operator_idle,
    should_auto_resume_ai,
)


def test_should_not_resume_when_ai_is_already_active() -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert (
        should_auto_resume_ai(
            human_takeover_active=False,
            operator_viewed_at=now - timedelta(hours=2),
            now=now,
        )
        is False
    )


def test_missing_view_and_activity_resumes_stuck_pause() -> None:
    assert should_auto_resume_ai(human_takeover_active=True) is True


def test_recent_operator_view_keeps_ai_paused() -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert (
        should_auto_resume_ai(
            human_takeover_active=True,
            operator_viewed_at=now - timedelta(seconds=30),
            now=now,
        )
        is False
    )


def test_idle_operator_view_resumes_ai() -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert (
        should_auto_resume_ai(
            human_takeover_active=True,
            operator_viewed_at=now - timedelta(seconds=OPERATOR_IDLE_RESUME_SECONDS),
            now=now,
        )
        is True
    )


def test_waiting_queue_uses_escalation_time_not_instant_resume() -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert (
        should_auto_resume_ai(
            human_takeover_active=True,
            last_activity=now - timedelta(seconds=10),
            now=now,
        )
        is False
    )


def test_old_operator_send_without_view_resumes() -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    assert (
        should_auto_resume_ai(
            human_takeover_active=True,
            last_activity=now - timedelta(hours=1),
            now=now,
        )
        is True
    )


@pytest.mark.asyncio
async def test_auto_resume_calls_resume_manual_mode() -> None:
    resume = AsyncMock()
    conv = {
        "human_takeover_active": True,
        "last_updated": datetime(2026, 9, 12, 10, 0, tzinfo=UTC),
    }
    with (
        patch("services.requests.manual_mode.resume_manual_mode", resume),
        patch("services.live_chat_service.live_chat_service.invalidate_cache"),
        patch(
            "services.live_chat_service.live_chat_service._refresh_index_for_conversation",
            new_callable=AsyncMock,
        ),
    ):
        did = await auto_resume_if_operator_idle(
            conv_data=conv,
            user_id="instagram:1",
            conversation_id="c1",
            tenant_id=None,
            source_channel="instagram",
        )
    assert did is True
    resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_resume_skips_when_operator_is_viewing() -> None:
    resume = AsyncMock()
    now = datetime.now(UTC)
    conv = {"human_takeover_active": True, "operator_viewed_at": now}
    with patch("services.requests.manual_mode.resume_manual_mode", resume):
        did = await auto_resume_if_operator_idle(
            conv_data=conv,
            user_id="instagram:1",
            conversation_id="c1",
            tenant_id=None,
            source_channel="instagram",
        )
    assert did is False
    resume.assert_not_awaited()
