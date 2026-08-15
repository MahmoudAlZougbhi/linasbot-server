"""LOC split: event_handlers jobs/scheduler under 500 lines."""

from __future__ import annotations

from pathlib import Path


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


def test_meta_deletion_reconcile_runs_per_node_without_cluster_singleton_lock() -> None:
    source = Path("modules/meta_data_deletion_reconcile_job.py").read_text(encoding="utf-8")
    scheduler_source = Path("modules/event_handlers_scheduler.py").read_text(encoding="utf-8")
    assert "try_acquire_job_lock" not in source
    assert 'id="meta_data_deletion_reconcile"' in scheduler_source
