"""LOC split: event_handlers jobs/scheduler under 500 lines."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_event_handlers_modules_under_500_lines() -> None:
    assert _line_count("modules/event_handlers.py") < 500
    assert _line_count("modules/event_handlers_populate_jobs.py") < 500
    assert _line_count("modules/event_handlers_monitor_jobs.py") < 500
    assert _line_count("modules/event_handlers_scheduler.py") < 500
    assert _line_count("modules/meta_data_deletion_reconcile_job.py") < 500


def test_event_handlers_preserves_job_exports() -> None:
    from modules import event_handlers
    from modules.event_handlers_monitor_jobs import monitor_smart_messages_job
    from modules.event_handlers_populate_jobs import populate_messages_job
    from modules.event_handlers_scheduler import start_smart_messaging_scheduler
    from modules.meta_data_deletion_reconcile_job import run_meta_data_deletion_reconcile_job

    assert callable(event_handlers.startup_event)
    assert callable(event_handlers.shutdown_event)
    assert callable(populate_messages_job)
    assert callable(monitor_smart_messages_job)
    assert callable(start_smart_messaging_scheduler)
    assert callable(run_meta_data_deletion_reconcile_job)


def test_meta_registry_startup_repair_is_local_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules import event_handlers
    from services import meta_app_registry

    registry = Mock()
    monkeypatch.setattr(meta_app_registry, "meta_multi_app_registry_enabled", lambda: True)
    monkeypatch.setattr(meta_app_registry, "get_meta_app_registry", lambda: registry)

    event_handlers.repair_meta_registry_before_readiness()

    registry.archive_superseded_duplicate_bindings.assert_called_once_with(actor_id="meta-registry-startup-repair")
    registry.archive_superseded_duplicate_bindings.side_effect = RuntimeError("repair failed")
    with pytest.raises(RuntimeError, match="repair failed"):
        event_handlers.repair_meta_registry_before_readiness()


def test_meta_registry_repair_precedes_other_startup_work() -> None:
    source = Path("modules/event_handlers.py").read_text(encoding="utf-8")
    startup = source[source.index("async def startup_event") : source.index('@app.on_event("shutdown")')]
    assert startup.index("repair_meta_registry_before_readiness()") < startup.index("assert_no_monty_cloud_dual_bind()")


def test_meta_deletion_reconcile_runs_per_node_without_cluster_singleton_lock() -> None:
    source = Path("modules/meta_data_deletion_reconcile_job.py").read_text(encoding="utf-8")
    scheduler_source = Path("modules/event_handlers_scheduler.py").read_text(encoding="utf-8")
    assert "try_acquire_job_lock" not in source
    assert 'id="meta_data_deletion_reconcile"' in scheduler_source


def test_scheduler_does_not_register_channel_comment_polls() -> None:
    scheduler_source = Path("modules/event_handlers_scheduler.py").read_text(encoding="utf-8")
    assert "tiktok_comment_sync_tick" not in scheduler_source
    assert "meta_social_comment_sync_tick" not in scheduler_source
    assert "run_tiktok_comment_sync_job" not in scheduler_source
    assert "run_meta_social_comment_sync_job" not in scheduler_source
    assert 'id="tiktok_comment_webhook_register"' in scheduler_source
    assert "webhook-only" in scheduler_source
