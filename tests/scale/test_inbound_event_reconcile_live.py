"""Watchdog must not mint a second job while ingress idempotency still owns one."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.scale.inbound_event_reconcile import _requeue_one_stuck, reconcile_stuck_inbound_events
from services.scale.inbound_event_reconcile_live import action_if_ingress_job_already_owns


def _record() -> SimpleNamespace:
    return SimpleNamespace(
        event_id="ibe_" + "a" * 40,
        kind="meta_dm",
        tenant_id="linas",
        conversation_key="linas:facebook:customer",
        attempts=1,
        claim_key="facebook:provider-mid",
        payload={},
        binding_snapshot={},
        settings_snapshot={},
        last_error=None,
    )


def test_live_queued_ingress_job_skips_requeue(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _record()
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.lookup_ingress_job",
        lambda _rec: SimpleNamespace(id="job-ingress", status="queued"),
    )
    marks: list[dict[str, object]] = []
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.mark_inbound_state",
        lambda *_args, **kwargs: marks.append(kwargs),
    )

    assert action_if_ingress_job_already_owns(rec) == {  # type: ignore[arg-type]
        "event_id": rec.event_id,
        "action": "ingress_job_live",
        "job_id": "job-ingress",
        "status": "queued",
    }
    assert marks == []


def test_completed_ingress_job_catchup_marks_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _record()
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.lookup_ingress_job",
        lambda _rec: SimpleNamespace(id="job-done", status="completed"),
    )
    marks: list[dict[str, object]] = []
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.mark_inbound_state",
        lambda *_args, **kwargs: marks.append(kwargs),
    )

    assert action_if_ingress_job_already_owns(rec) == {  # type: ignore[arg-type]
        "event_id": rec.event_id,
        "action": "ledger_catchup_completed",
        "job_id": "job-done",
    }
    assert marks == [{"state": "completed", "last_error": "reconcile_catchup_redis_completed"}]


def test_requeue_one_does_not_claim_when_ingress_job_live(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _record()
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile._disarmed_soak_action",
        lambda _rec: None,
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.action_if_ingress_job_already_owns",
        lambda _rec: {"event_id": rec.event_id, "action": "ingress_job_live", "job_id": "j1", "status": "processing"},
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("watchdog claimed while ingress job still live")

    monkeypatch.setattr("services.durable_event_claim.try_claim_event_handle", boom)

    assert _requeue_one_stuck(rec)["action"] == "ingress_job_live"  # type: ignore[arg-type]


def test_reconcile_skips_firestore_scan_while_soak_armed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.scale.soak_arm.is_armed", lambda: True)
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile.list_active_inbound_events",
        lambda **_kwargs: pytest.fail("soak-armed reconcile scanned active Firestore rows"),
    )

    result = reconcile_stuck_inbound_events()

    assert result["soak_armed_skip"] is True
    assert result["examined"] == 0
    assert result["actions"] == []
