"""Dedicated-thread job-lease refresh so a blocked event loop cannot look like a dead worker."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from services.queues.job_lease import lease_log
from services.scale.metrics import incr, set_gauge

RefreshFn = Callable[[], str]


class ThreadLeaseHeartbeat:
    """Refresh the Redis lease off the asyncio loop (OpenAI/sync work cannot starve it)."""

    def __init__(
        self,
        *,
        refresh: RefreshFn,
        interval_seconds: float,
        job_id: str = "",
        worker_id: str = "",
    ) -> None:
        self._refresh = refresh
        self._interval = max(0.05, float(interval_seconds))
        self._job_id = job_id
        self._worker_id = worker_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_ok_at = 0.0
        self.lag_seconds = 0.0
        self._logged_retry = False

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-hb-{self._job_id[:12] or 'job'}",
            daemon=True,
        )
        self._thread.start()

    def _metric(self, name: str, *, gauge: float | None = None) -> None:
        try:
            if gauge is None:
                incr(name)
            else:
                set_gauge(name, gauge)
        except Exception:
            return

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            result = "retry"
            try:
                result = str(self._refresh() or "retry")
            except Exception:
                result = "retry"
            lag = max(0.0, time.monotonic() - started)
            self.lag_seconds = lag
            self._metric("heartbeat_lag", gauge=lag)
            if self._worker_id:
                self._metric("worker_last_seen", gauge=time.time())
            if result == "ok":
                self.last_ok_at = time.time()
                self._logged_retry = False
                self._metric("lease_refresh_success")
            elif result == "stolen":
                self._metric("lease_refresh_failure")
                lease_log("heartbeat_stop_stolen", job_id=self._job_id, extra=self._worker_id)
                return
            else:
                self._metric("lease_refresh_failure")
                if not self._logged_retry:
                    self._logged_retry = True
                    lease_log("heartbeat_refresh_retry", job_id=self._job_id, extra=self._worker_id)
            self._stop.wait(self._interval)

    def stop(self, *, timeout_seconds: float = 1.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.05, timeout_seconds))


def bind_claimed_heartbeat(
    *,
    backend: Any,
    job: Any,
    worker_id: str,
    interval_seconds: float,
    extra: Callable[[], None] | None = None,
) -> ThreadLeaseHeartbeat:
    job_id = str(job.id)
    token = str(getattr(job, "lease_token", "") or "")
    owner = str(worker_id or "")

    def _refresh() -> str:
        try:
            from services.scale.job_progress import heartbeat_should_stop

            redis_client = getattr(backend, "_r", None)
            if heartbeat_should_stop(job_id, token, redis_client=redis_client):
                return "stolen"
        except Exception:
            pass
        if extra is not None:
            try:
                extra()
            except Exception:
                pass
        try:
            if backend.refresh_lease(job_id, owner, token):
                return "ok"
        except Exception:
            return "retry"
        try:
            stored = backend.get(job_id)
        except Exception:
            return "retry"
        if stored is None or str(stored.status) != "processing":
            return "stolen"
        if str(stored.lease_token or "") != token or str(stored.lease_owner or "") != owner:
            return "stolen"
        return "retry"

    beat = ThreadLeaseHeartbeat(
        refresh=_refresh,
        interval_seconds=interval_seconds,
        job_id=job_id,
        worker_id=owner,
    )
    beat.start()
    return beat
