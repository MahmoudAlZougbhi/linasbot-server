"""Dedicated-thread job-lease refresh so a blocked event loop cannot look like a dead worker."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from services.scale.metrics import incr, set_gauge

RefreshFn = Callable[[], bool]


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

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-hb-{self._job_id[:12] or 'job'}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            ok = False
            try:
                ok = bool(self._refresh())
            except Exception:
                ok = False
            lag = max(0.0, time.monotonic() - started)
            self.lag_seconds = lag
            try:
                set_gauge("heartbeat_lag", lag)
                if self._worker_id:
                    set_gauge("worker_last_seen", time.time())
            except Exception:
                pass
            if ok:
                self.last_ok_at = time.time()
                incr("lease_refresh_success")
            else:
                incr("lease_refresh_failure")
                return
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

    def _refresh() -> bool:
        try:
            from services.scale.job_progress import heartbeat_should_stop

            redis_client = getattr(backend, "_r", None)
            if heartbeat_should_stop(job_id, token, redis_client=redis_client):
                return False
        except Exception:
            pass
        if extra is not None:
            extra()
        return bool(backend.refresh_lease(job_id, worker_id, token))

    beat = ThreadLeaseHeartbeat(
        refresh=_refresh,
        interval_seconds=interval_seconds,
        job_id=job_id,
        worker_id=worker_id,
    )
    beat.start()
    return beat
