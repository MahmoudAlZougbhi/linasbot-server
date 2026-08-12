"""Durability: accepted Meta events survive Valkey/worker restart via ledger + reconcile."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.scale.inbound_event_reconcile import reconcile_stuck_inbound_events
from services.scale.inbound_event_store import (
    InboundEventRecord,
    accountability_stats,
    get_inbound_event,
    list_active_inbound_events,
    mark_inbound_state,
    put_inbound_event,
    stable_event_id,
)


@pytest.fixture()
def inbound_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    # Force persistent_storage to re-resolve for this process is hard; write via store
    # after monkeypatching LOGS_DIR used by store.
    import services.scale.inbound_event_store as store

    logs = tmp_path / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "LOGS_DIR", logs)
    monkeypatch.setattr(store, "ensure_dirs", lambda: None)
    return logs


def test_accepted_event_survives_fake_valkey_loss(inbound_root: Path) -> None:
    claim_key = "tenant:ig:mid-durability-1"
    event_id = stable_event_id("meta_dm", claim_key)
    now = time.time()
    put_inbound_event(
        InboundEventRecord(
            event_id=event_id,
            kind="meta_dm",
            tenant_id="linas",
            claim_namespace="meta_social_dm_global",
            claim_key=claim_key,
            state="accepted",
            created_at=now - 120,
            updated_at=now - 120,
            payload={"message_id": "mid-durability-1", "text": "hello"},
            settings_snapshot={"tenant_id": "linas"},
            conversation_key="linas:instagram:psid",
        )
    )
    # Simulate Valkey flush: only durable ledger remains.
    loaded = get_inbound_event(event_id)
    assert loaded is not None
    assert loaded.state == "accepted"
    assert loaded.payload["message_id"] == "mid-durability-1"

    # Age filter: put_inbound_event stamps updated_at=now; use 0 for immediate reconcile proof.
    result = reconcile_stuck_inbound_events(older_than_seconds=0.0)
    assert result["examined"] >= 1
    assert result["unexplained_missing_events"] == 0
    refreshed = get_inbound_event(event_id)
    assert refreshed is not None
    assert refreshed.state in {"accepted", "queued"}
    assert refreshed.attempts >= 1

    stats = accountability_stats()
    assert stats["unexplained_missing_events"] == 0
    assert stats["accepted_total"] >= 1


def test_terminal_completion_removes_from_active(inbound_root: Path) -> None:
    claim_key = "tenant:ig:mid-done"
    event_id = stable_event_id("meta_dm", claim_key)
    now = time.time()
    put_inbound_event(
        InboundEventRecord(
            event_id=event_id,
            kind="meta_dm",
            tenant_id="linas",
            claim_namespace="meta_social_dm_global",
            claim_key=claim_key,
            state="processing",
            created_at=now - 200,
            updated_at=now - 200,
            payload={"message_id": "mid-done"},
        )
    )
    mark_inbound_state(event_id, state="completed", ai_output_persisted=True, outbound_status="sent")
    active = list_active_inbound_events(older_than_seconds=0.0)
    assert all(r.event_id != event_id for r in active)
    stats = accountability_stats()
    assert stats["unexplained_missing_events"] == 0


def test_max_attempts_dead_letters(inbound_root: Path) -> None:
    claim_key = "tenant:ig:mid-dlq"
    event_id = stable_event_id("meta_dm", claim_key)
    now = time.time()
    put_inbound_event(
        InboundEventRecord(
            event_id=event_id,
            kind="meta_dm",
            tenant_id="linas",
            claim_namespace="meta_social_dm_global",
            claim_key=claim_key,
            state="failed",
            created_at=now - 500,
            updated_at=now - 500,
            payload={"message_id": "mid-dlq"},
            attempts=8,
            last_error="boom",
        )
    )
    result = reconcile_stuck_inbound_events(older_than_seconds=0.0)
    assert any(a.get("action") == "dead_letter" and a.get("event_id") == event_id for a in result["actions"])
    rec = get_inbound_event(event_id)
    assert rec is not None
    assert rec.state == "dead_letter"
