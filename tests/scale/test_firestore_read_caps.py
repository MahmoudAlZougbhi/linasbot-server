"""The reconcile watchdog must not bill a full collection read on every pass."""

from __future__ import annotations

import time

from services.scale.inbound_active_scan import RECONCILE_LOCK_TTL_SECONDS, shared_active_records
from services.scale.inbound_event_store_models import InboundEventRecord


def _records(count: int) -> list[dict]:
    now = time.time()
    return [
        InboundEventRecord(
            event_id=f"ibe_{index}",
            kind="meta_dm",
            tenant_id="linas",
            claim_namespace="ns",
            claim_key=f"k{index}",
            state="queued",
            created_at=now,
            updated_at=now,
        ).to_dict()
        for index in range(count)
    ]


class _Snapshot:
    def __init__(self, data: dict) -> None:
        self._data = data
        self.exists = True

    def to_dict(self) -> dict:
        return self._data


class _EmptyDocument:
    exists = False

    def to_dict(self) -> None:
        return None


class _CountingCollection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.streamed = 0

    def where(self, *, filter: object) -> _CountingCollection._Query:
        del filter
        return self._Query(self)

    def document(self, event_id: str) -> object:
        del event_id

        class _Ref:
            def get(self) -> _EmptyDocument:
                return _EmptyDocument()

        return _Ref()

    class _Query:
        def __init__(self, parent: _CountingCollection, capped: int | None = None) -> None:
            self.parent = parent
            self.capped = capped

        def limit(self, count: int) -> _CountingCollection._Query:
            return self.parent._Query(self.parent, count)

        def stream(self, timeout: float | None = None, retry: object = None) -> list[_Snapshot]:
            del timeout, retry
            rows = self.parent.rows if self.capped is None else self.parent.rows[: self.capped]
            self.parent.streamed = len(rows)
            return [_Snapshot(row) for row in rows]


def test_capped_active_scan_reads_32_of_80_documents() -> None:
    unlimited = _CountingCollection(_records(80))
    shared_active_records(unlimited, local_event_ids=set(), query_limit=None)
    capped = _CountingCollection(_records(80))
    found = shared_active_records(capped, local_event_ids=set(), query_limit=32)
    assert unlimited.streamed == 80
    assert capped.streamed == 32
    assert len(found) == 32


def test_inbound_watchdog_does_not_release_the_cluster_lock(monkeypatch) -> None:
    import modules.inbound_event_reconcile_job as job

    held: dict[str, float] = {}
    scans: list[str] = []

    def acquire(name: str, *, ttl_seconds: float) -> bool:
        if name in held:
            return False
        held[name] = ttl_seconds
        return True

    monkeypatch.setattr(job, "try_acquire_job_lock", acquire)
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile.reconcile_stuck_inbound_events",
        lambda **_kwargs: scans.append("inbound") or {"examined": 0, "actions": [], "unexplained_missing_events": 0},
    )
    monkeypatch.setattr(
        "services.integrations.omnichannel.reconcile.reconcile_omnichannel",
        lambda **_kwargs: {"examined": 0, "actions": []},
    )

    job._run_inbound_event_reconcile_job_sync()
    job._run_inbound_event_reconcile_job_sync()

    assert scans == ["inbound"]
    assert held["inbound_event_reconcile"] == RECONCILE_LOCK_TTL_SECONDS


def test_quota_backoff_grows_and_clears(monkeypatch) -> None:
    from services.scale import firestore_quota_backoff as backoff

    monkeypatch.setattr(backoff, "_redis", lambda: None)
    backoff._level = 0
    backoff._local_until = 0.0
    monkey_now = 1_000.0
    first = backoff.note_quota_failure(now=monkey_now)
    assert first == monkey_now + 60
    assert backoff.quota_backoff_active(now=monkey_now + 30) is True
    second = backoff.note_quota_failure(now=monkey_now)
    assert second == monkey_now + 120
    cause = ConnectionError("429 Quota exceeded.")
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = cause
    assert backoff.is_quota_error(wrapped) is True
    backoff.note_quota_success()
    assert backoff.quota_backoff_active(now=monkey_now + 30) is False
    backoff._level = 0
    backoff._local_until = 0.0


def test_interval_lock_stays_held_after_success_and_releases_on_error(monkeypatch) -> None:
    from services.scale.job_interval_lock import job_interval_lock

    released: list[str] = []
    held: set[str] = set()

    def acquire(name: str, *, ttl_seconds: float) -> bool:
        del ttl_seconds
        if name in held:
            return False
        held.add(name)
        return True

    monkeypatch.setattr("services.scale.job_interval_lock.try_acquire_job_lock", acquire)
    monkeypatch.setattr("services.scale.job_interval_lock.release_job_lock", lambda name: released.append(name))

    with job_interval_lock("sample", ttl_seconds=50) as first:
        assert first is True
    with job_interval_lock("sample", ttl_seconds=50) as second:
        assert second is False
    assert released == []

    held.clear()
    try:
        with job_interval_lock("sample", ttl_seconds=50) as acquired:
            assert acquired is True
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert released == ["sample"]


def test_deletion_scan_asks_only_for_pending_requests(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class _Query:
        def where(self, *, filter: object) -> _Query:
            seen["filter"] = filter
            return self

        def stream(self, timeout: float | None = None, retry: object = None) -> list[object]:
            del timeout, retry
            seen["streamed"] = True
            return []

    class _App:
        def collection(self, name: str) -> _Query:
            seen["collection"] = name
            return _Query()

    monkeypatch.setattr(
        "services.integrations.meta.meta_data_deletion_process._firestore_db",
        lambda: object(),
    )
    monkeypatch.setattr(
        "services.integrations.meta.meta_data_deletion_process._app_document",
        lambda _db: _App(),
    )
    monkeypatch.setattr(
        "services.integrations.meta.meta_data_deletion_process._deletion_node_config",
        lambda: ("node01", ["node01", "node02"]),
    )
    from services.integrations.meta.meta_data_deletion_process import process_pending_meta_deletion_requests

    stats = process_pending_meta_deletion_requests()
    pending_filter = seen["filter"]
    assert seen["collection"] == "meta_deletion_requests"
    assert seen["streamed"] is True
    assert getattr(pending_filter, "value", None) == "pending"
    assert stats["examined"] == 0
