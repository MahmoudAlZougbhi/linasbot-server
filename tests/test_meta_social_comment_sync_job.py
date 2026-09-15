"""Tests: leftover comment-sync queue jobs stay webhook-only. Poll stubs are gone."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.integrations.meta.meta_social_comment_sync_jobs import handle_meta_social_comment_sync
from services.integrations.tiktok.jobs import handle_tiktok_comment_sync
from services.queues.models import QueueJob

ROOT = Path(__file__).resolve().parents[1]


def test_comment_poll_stub_modules_are_gone() -> None:
    assert not (ROOT / "modules/meta_social_comment_sync_job.py").exists()
    assert not (ROOT / "modules/tiktok_sync_job.py").exists()


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
