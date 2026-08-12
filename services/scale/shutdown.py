"""Graceful shutdown / drain coordinator for API and workers."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ShutdownCoordinator:
    """
    On SIGTERM / deploy:
    - mark not-ready
    - stop accepting new queue work
    - wait for in-flight requests/jobs (bounded)
    - close DB engines when asked
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._draining = False
        self._accept_queue_work = True
        self._inflight_http = 0
        self._inflight_jobs = 0
        self._started_drain_at: float | None = None

    @property
    def draining(self) -> bool:
        with self._lock:
            return self._draining

    @property
    def accept_queue_work(self) -> bool:
        with self._lock:
            return self._accept_queue_work and not self._draining

    def begin_drain(self) -> None:
        with self._lock:
            if self._draining:
                return
            self._draining = True
            self._accept_queue_work = False
            self._started_drain_at = time.time()
            logger.info("shutdown_coordinator: drain started")

    def track_http_enter(self) -> bool:
        """Return False when draining (caller should 503)."""
        with self._lock:
            if self._draining:
                return False
            self._inflight_http += 1
            return True

    def track_http_exit(self) -> None:
        with self._lock:
            self._inflight_http = max(0, self._inflight_http - 1)

    def track_job_enter(self) -> bool:
        with self._lock:
            if not self._accept_queue_work:
                return False
            self._inflight_jobs += 1
            return True

    def track_job_exit(self) -> None:
        with self._lock:
            self._inflight_jobs = max(0, self._inflight_jobs - 1)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "draining": self._draining,
                "accept_queue_work": self._accept_queue_work,
                "inflight_http": self._inflight_http,
                "inflight_jobs": self._inflight_jobs,
                "drain_age_seconds": (
                    None if self._started_drain_at is None else max(0.0, time.time() - self._started_drain_at)
                ),
            }

    def wait_for_idle(self, *, timeout_seconds: float | None = None) -> bool:
        timeout = timeout_seconds
        if timeout is None:
            try:
                timeout = float(os.getenv("LINAS_DRAIN_TIMEOUT_SECONDS") or "45")
            except ValueError:
                timeout = 45.0
        deadline = time.time() + max(1.0, timeout)
        while time.time() < deadline:
            snap = self.snapshot()
            if snap["inflight_http"] == 0 and snap["inflight_jobs"] == 0:
                return True
            time.sleep(0.05)
        return False

    async def await_idle(self, *, timeout_seconds: float | None = None) -> bool:
        return await asyncio.to_thread(self.wait_for_idle, timeout_seconds=timeout_seconds)


shutdown_coordinator = ShutdownCoordinator()
