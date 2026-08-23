"""Tests for HA-safe Meta social comment sync tick scheduling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from modules.meta_social_comment_sync_job import run_meta_social_comment_sync_job


@pytest.mark.asyncio
async def test_meta_social_comment_sync_tick_skips_when_ha_lock_held(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueue = MagicMock()
    monkeypatch.setattr("modules.meta_social_comment_sync_job.try_acquire_job_lock", lambda *_a, **_k: False)
    monkeypatch.setattr("modules.meta_social_comment_sync_job.release_job_lock", MagicMock())
    monkeypatch.setattr("modules.meta_social_comment_sync_job.job_queue", type("JQ", (), {"enqueue": enqueue})())

    await run_meta_social_comment_sync_job()

    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_meta_social_comment_sync_tick_enqueues_once_per_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    released: list[str] = []
    enqueue = MagicMock()
    binding = type(
        "B",
        (),
        {
            "binding_id": "bind_fb",
            "tenant_id": "linas",
            "app_key": "linas_first_party",
            "status": "active",
            "channel": "facebook",
        },
    )()

    monkeypatch.setattr("modules.meta_social_comment_sync_job.try_acquire_job_lock", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "modules.meta_social_comment_sync_job.release_job_lock",
        lambda key: released.append(key),
    )
    monkeypatch.setattr(
        "modules.meta_social_comment_sync_job.get_meta_app_registry",
        lambda: type("R", (), {"list_bindings": lambda *a, **k: [binding]})(),
    )
    monkeypatch.setattr("modules.meta_social_comment_sync_job.APP_A_KEY", "linas_first_party")
    monkeypatch.setattr("modules.meta_social_comment_sync_job.job_queue", type("JQ", (), {"enqueue": enqueue})())
    monkeypatch.setattr("modules.meta_social_comment_sync_job.time.time", lambda: 120.0)

    await run_meta_social_comment_sync_job()

    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["job_type"] == "meta_social_comment_sync"
    assert enqueue.call_args.kwargs["payload"] == {"binding_id": "bind_fb", "channel": "facebook"}
    assert enqueue.call_args.kwargs["idempotency_key"] == "meta_comment_sync:bind_fb:2"
    assert released == ["meta_social_comment_sync_tick"]
