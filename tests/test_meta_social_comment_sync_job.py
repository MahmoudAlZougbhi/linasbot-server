"""Tests: Meta/TikTok comment Graph poll is removed. Inbound is webhook-only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules.meta_social_comment_sync_job import (
    meta_comment_poll_enabled,
    run_meta_social_comment_sync_job,
)
from modules.tiktok_sync_job import run_tiktok_comment_sync_job
from services.meta_social_comment_sync_jobs import handle_meta_social_comment_sync
from services.queues.models import QueueJob
from services.tiktok_business.jobs import handle_tiktok_comment_sync


def test_meta_comment_poll_stays_off_even_when_env_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_COMMENT_POLL_ENABLED", "true")
    monkeypatch.setenv("META_COMMENT_POLL_INTERVAL_SECONDS", "15")
    assert meta_comment_poll_enabled() is False


def test_meta_comment_poll_job_module_does_not_enqueue() -> None:
    source = Path("modules/meta_social_comment_sync_job.py").read_text(encoding="utf-8")
    assert "job_queue" not in source
    assert "enqueue" not in source


def test_tiktok_comment_poll_job_module_does_not_enqueue() -> None:
    source = Path("modules/tiktok_sync_job.py").read_text(encoding="utf-8")
    assert "job_queue" not in source
    assert "enqueue" not in source


@pytest.mark.asyncio
async def test_meta_social_comment_sync_tick_never_enqueues(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueue = MagicMock()
    monkeypatch.setattr(
        "services.job_queue.job_queue",
        type("JQ", (), {"enqueue": enqueue})(),
        raising=False,
    )
    await run_meta_social_comment_sync_job()
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_tiktok_comment_sync_tick_never_enqueues(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueue = MagicMock()
    monkeypatch.setattr(
        "services.job_queue.job_queue",
        type("JQ", (), {"enqueue": enqueue})(),
        raising=False,
    )
    await run_tiktok_comment_sync_job()
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_leftover_meta_comment_sync_job_is_webhook_only() -> None:
    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_social_comment_sync",
        tenant_id="linas",
        payload={"binding_id": "bind_fb", "channel": "facebook"},
    )
    result = await handle_meta_social_comment_sync(job)
    assert result["skipped"] is True
    assert result["reason"] == "webhook_only"


@pytest.mark.asyncio
async def test_leftover_tiktok_comment_sync_job_is_webhook_only() -> None:
    job = QueueJob.new(
        queue="background",
        job_type="tiktok_comment_sync",
        tenant_id="linas",
        payload={"connection_id": "conn_1"},
    )
    result = await handle_tiktok_comment_sync(job)
    assert result["skipped"] is True
    assert result["reason"] == "webhook_only"
