"""Redis adapter implementing DurableQueue (wraps existing RedisQueueBackend)."""

from __future__ import annotations

import time
from typing import Any

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.queue_protocol import QueueMetrics


class RedisDurableQueue:
    """Launch-time durable queue. Swap later via DurableQueue protocol (e.g. Kafka)."""

    backend_name = "redis"

    def __init__(self, backend: RedisQueueBackend | None = None) -> None:
        self._backend = backend or RedisQueueBackend()

    def enqueue(self, job: QueueJob) -> QueueJob:
        return self._backend.enqueue(job)

    def claim(self, queue: str, *, worker_id: str, timeout: int = 5) -> QueueJob | None:
        return self._backend.claim(queue, worker_id=worker_id, timeout=timeout)

    def complete(self, job: QueueJob) -> None:
        self._backend.complete(job)

    def fail(self, job: QueueJob, *, error: str, retry: bool) -> bool:
        return self._backend.fail(job, error=error, retry=retry)

    def requeue_soft(self, job: QueueJob, *, delay_seconds: float = 1.0) -> None:
        self._backend.requeue_soft(job, delay_seconds=delay_seconds)

    def depth(self) -> dict[str, int]:
        return self._backend.depth()

    def metrics(self) -> QueueMetrics:
        depth = self._backend.depth()
        oldest: dict[str, float] = {}
        dlq: dict[str, int] = {}
        now = time.time()
        for name, count in list(depth.items()):
            if name.endswith("_dlq"):
                dlq[name[: -len("_dlq")]] = int(count)
            elif name.endswith("_processing"):
                continue
            else:
                # Approximate age via job available_at when peek is unavailable.
                oldest[name] = 0.0 if int(count) == 0 else max(0.0, now - self._oldest_approx(name))
        return QueueMetrics(depth_by_queue=depth, oldest_age_seconds=oldest, dlq_by_queue=dlq)

    def _oldest_approx(self, queue: str) -> float:
        """Best-effort oldest enqueue time from list head job document."""
        try:
            r = self._backend._r  # noqa: SLF001
            from services.queues.config import key_prefix

            job_id = r.lindex(f"{key_prefix()}:queue:{queue}", -1)
            if not job_id:
                return time.time()
            job = self._backend.get(str(job_id))
            if job is None:
                return time.time()
            return float(getattr(job, "created_at", time.time()) or time.time())
        except Exception:
            return time.time()

    def ping(self) -> bool:
        return bool(self._backend.ping())

    def throttle_provider(self, *, provider: str, limit_per_minute: int) -> bool:
        return self._backend.throttle_provider(provider=provider, limit_per_minute=limit_per_minute)

    def raw(self) -> Any:
        return self._backend
