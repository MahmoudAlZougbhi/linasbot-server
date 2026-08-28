"""Reopen Meta DMs that completed without a Graph send."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.scale.inbound_event_store import InboundEventRecord, get_inbound_event, put_inbound_event
from services.scale.inbound_undelivered import (
    is_completed_undelivered,
    list_completed_undelivered_meta_dms,
    reopen_completed_undelivered,
)


@pytest.fixture()
def inbound_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    logs = tmp_path / "logs"
    inbound = logs / "inbound_events"
    inbound.mkdir(parents=True)
    import services.scale.inbound_event_store as inbound_store

    monkeypatch.setattr(inbound_store, "LOGS_DIR", logs)
    monkeypatch.setattr(inbound_store, "ensure_dirs", lambda: None)
    return logs


def _record(*, event_id: str, state: str, outbound: str | None, age: float = 120.0) -> InboundEventRecord:
    now = time.time()
    return InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key=f"linas:facebook:{event_id}",
        state=state,  # type: ignore[arg-type]
        created_at=now - age,
        updated_at=now - age,
        payload={"message_id": "mid-1", "channel": "facebook", "sender_id": "psid-1", "text": "hi"},
        conversation_key="facebook:psid-1",
        outbound_status=outbound,
    )


def test_completed_unknown_is_undelivered(inbound_logs: Path) -> None:
    rec = put_inbound_event(_record(event_id="ibe_unknown", state="completed", outbound="unknown"))
    assert is_completed_undelivered(rec) is True
    found = list_completed_undelivered_meta_dms(older_than_seconds=0.0)
    assert [item.event_id for item in found] == ["ibe_unknown"]


def test_delivered_completed_is_not_undelivered(inbound_logs: Path) -> None:
    rec = put_inbound_event(_record(event_id="ibe_sent", state="completed", outbound="delivered"))
    assert is_completed_undelivered(rec) is False
    assert list_completed_undelivered_meta_dms(older_than_seconds=0.0) == []


def test_reopen_completed_unknown_becomes_accepted(inbound_logs: Path) -> None:
    put_inbound_event(_record(event_id="ibe_reopen", state="completed", outbound="needs_owner_action"))
    opened = reopen_completed_undelivered("ibe_reopen")
    assert opened.state == "accepted"
    assert opened.outbound_status == "undelivered_retry"
    live = get_inbound_event("ibe_reopen")
    assert live is not None
    assert live.state == "accepted"


def test_list_keeps_local_when_shared_get_fails(inbound_logs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    put_inbound_event(_record(event_id="ibe_local", state="completed", outbound="unknown"))

    def _boom(event_id: str, **_kwargs: object) -> None:
        raise RuntimeError("firestore down")

    monkeypatch.setattr("services.scale.inbound_undelivered.get_inbound_event", _boom)
    found = list_completed_undelivered_meta_dms(older_than_seconds=0.0)
    assert [item.event_id for item in found] == ["ibe_local"]
