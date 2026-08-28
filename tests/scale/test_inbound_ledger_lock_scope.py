"""Local inbound flock must not be held across Firestore persist."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import services.scale.inbound_event_store as event_store
from services.scale.inbound_event_store import InboundEventRecord


def _record(event_id: str) -> InboundEventRecord:
    now = time.time()
    return InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key=f"facebook:{event_id}",
        state="accepted",
        created_at=now,
        updated_at=now,
        payload={"channel": "facebook", "text": "customer content"},
        settings_snapshot={"binding_id": "binding-lock-1"},
        binding_snapshot={"binding_id": "binding-lock-1"},
    )


def test_create_releases_flock_before_firestore(monkeypatch, tmp_path: Path) -> None:
    import services.meta_inbound_deletion_fence as fence
    import utils.utils

    root = tmp_path / "inbound"
    root.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: object())
    monkeypatch.setenv("ENVIRONMENT", "production")

    started = threading.Event()
    release = threading.Event()
    lock_acquired = threading.Event()

    def slow_create(*, binding_id: str, event_id: str, document: dict) -> tuple[dict, bool]:
        started.set()
        assert release.wait(2.0)
        return dict(document), True

    monkeypatch.setattr(fence, "create_firestore_event_unless_fenced", slow_create)

    def hold_lock() -> None:
        with event_store.local_inbound_event_ledger_lock():
            lock_acquired.set()

    worker = threading.Thread(
        target=event_store.create_inbound_event,
        args=(_record("ibe_" + "a" * 40),),
        kwargs={"enforce_binding_deletion_fence": True},
        daemon=True,
    )
    worker.start()
    assert started.wait(2.0)
    locker = threading.Thread(target=hold_lock, daemon=True)
    locker.start()
    assert lock_acquired.wait(1.0), "ledger flock stayed held during Firestore persist"
    release.set()
    worker.join(2.0)
    locker.join(2.0)
    assert not worker.is_alive()


def test_put_releases_flock_before_firestore(monkeypatch, tmp_path: Path) -> None:
    import services.meta_inbound_deletion_fence as fence
    import utils.utils

    root = tmp_path / "inbound"
    root.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: object())
    monkeypatch.setenv("ENVIRONMENT", "production")

    started = threading.Event()
    release = threading.Event()
    lock_acquired = threading.Event()

    def slow_put(*, binding_id: str, event_id: str, document: dict) -> None:
        started.set()
        assert release.wait(2.0)

    monkeypatch.setattr(fence, "persist_firestore_event_unless_fenced", slow_put)

    def hold_lock() -> None:
        with event_store.local_inbound_event_ledger_lock():
            lock_acquired.set()

    worker = threading.Thread(
        target=event_store.put_inbound_event,
        args=(_record("ibe_" + "b" * 40),),
        kwargs={"enforce_binding_deletion_fence": True},
        daemon=True,
    )
    worker.start()
    assert started.wait(2.0)
    locker = threading.Thread(target=hold_lock, daemon=True)
    locker.start()
    assert lock_acquired.wait(1.0), "ledger flock stayed held during Firestore persist"
    release.set()
    worker.join(2.0)
    locker.join(2.0)
    assert not worker.is_alive()
