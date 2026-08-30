"""Measured duplicate-delivery faults on the Meta inbound ledger and Graph send."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

import services.scale.inbound_event_store as event_store
from services.meta_messaging import parse_meta_messaging_events
from services.scale.inbound_event_store import InboundEventRecord
from tests.meta_compliance_helpers import _FakeFirestore


@pytest.fixture()
def shared_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeFirestore:
    import utils.utils

    db = _FakeFirestore()
    root = tmp_path / "inbound"
    root.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setenv("ENVIRONMENT", "production")
    return db


def _record(event_id: str, *, payload: dict[str, Any] | None = None) -> InboundEventRecord:
    now = time.time()
    return InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key=f"facebook:page:{event_id}",
        state="queued",
        created_at=now,
        updated_at=now,
        payload=payload or {"channel": "facebook", "text": "hi", "message_id": "mid-1"},
        settings_snapshot={"binding_id": "binding-safety-1"},
        binding_snapshot={"binding_id": "binding-safety-1"},
    )


def test_one_hundred_redeliveries_create_one_firestore_row(shared_ledger: _FakeFirestore) -> None:
    event_id = "ibe_" + "d" * 40
    created_flags: list[bool] = []
    for _ in range(70):
        _row, created = event_store.create_inbound_event(
            _record(event_id),
            enforce_binding_deletion_fence=True,
        )
        created_flags.append(created)

    def _once() -> bool:
        _row, created = event_store.create_inbound_event(
            _record(event_id),
            enforce_binding_deletion_fence=True,
        )
        return created

    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(lambda _i: _once(), range(30)))
    created_flags.extend(concurrent)
    assert len(created_flags) == 100
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 99
    stored = (
        shared_ledger.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("inbound_events")
        .document(event_id)
        .data
    )
    assert stored is not None
    assert stored["event_id"] == event_id
    assert stored["state"] == "queued"


def test_meta_webhook_parse_cannot_inject_soak_flag() -> None:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "_linas_soak_simulation": True,
                "messaging": [
                    {
                        "sender": {"id": "user-1"},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1,
                        "message": {
                            "mid": "mid-inject",
                            "text": "hello",
                            "_linas_soak_simulation": True,
                        },
                    }
                ],
            }
        ],
    }
    events = parse_meta_messaging_events(payload, page_id="page-1")
    assert len(events) == 1
    assert events[0]["message_id"] == "mid-inject"
    assert "_linas_soak_simulation" not in events[0]


def test_two_nodes_share_one_row_via_firestore(
    shared_ledger: _FakeFirestore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_id = "ibe_" + "e" * 40
    node_a = tmp_path / "node-a"
    node_b = tmp_path / "node-b"
    node_a.mkdir()
    node_b.mkdir()

    def _create_on(root: Path) -> bool:
        monkeypatch.setattr(event_store, "_store_dir", lambda: root)
        _row, created = event_store.create_inbound_event(
            _record(event_id),
            enforce_binding_deletion_fence=True,
        )
        return created

    first = _create_on(node_a)
    second = _create_on(node_b)
    assert first is True
    assert second is False


def test_stale_worker_cannot_complete_after_lease_steal(monkeypatch: pytest.MonkeyPatch) -> None:
    import fakeredis

    from services.queues.models import QueueJob
    from services.queues.redis_backend import RedisQueueBackend

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = RedisQueueBackend()
    job = QueueJob.new(
        queue="high_priority", job_type="meta_inbound_process", tenant_id="linas", payload={"event_id": "ibe_x"}
    )
    backend.enqueue(job)
    old = backend.claim("high_priority", worker_id="w-old", timeout=1)
    assert old is not None
    fake.delete(backend._k("lease", old.id))
    assert backend.reclaim_expired_leases("high_priority") == 1
    new = backend.claim("high_priority", worker_id="w-new", timeout=1)
    assert new is not None
    assert backend.complete(old) == "stale_owner"
    assert backend.complete(new).startswith("ok")
    assert backend.get(old.id).status == "completed"
