"""Redis-backed durable queue (lists + hash job store + DLQ + heartbeats)."""

from __future__ import annotations

import json
import time
from typing import Any

from services.queues.config import (
    DEFAULT_MAX_ATTEMPTS,
    HEARTBEAT_TTL_SECONDS,
    QUEUE_NAMES,
    key_prefix,
    redis_url,
)
from services.queues.models import QueueJob


class RedisUnavailableError(RuntimeError):
    pass


def _client() -> Any:
    url = redis_url()
    if not url:
        raise RedisUnavailableError("REDIS_URL / LINAS_REDIS_URL is not configured")
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


class RedisQueueBackend:
    def __init__(self) -> None:
        self._r = _client()
        self.backend = "redis"
        self.production_ready = True

    def _k(self, *parts: str) -> str:
        return ":".join((key_prefix(), *parts))

    def enqueue(self, job: QueueJob) -> QueueJob:
        if job.idempotency_key:
            idem_key = self._k("idem", job.queue, job.tenant_id, job.idempotency_key)
            existing = self._r.get(idem_key)
            if existing:
                found = self.get(str(existing))
                if found is not None:
                    return found
        pipe = self._r.pipeline()
        pipe.hset(self._k("job", job.id), mapping={"data": json.dumps(job.to_dict())})
        pipe.lpush(self._k("queue", job.queue), job.id)
        if job.idempotency_key:
            pipe.set(
                self._k("idem", job.queue, job.tenant_id, job.idempotency_key),
                job.id,
                ex=60 * 60 * 24 * 7,
            )
        pipe.execute()
        return job

    def get(self, job_id: str) -> QueueJob | None:
        raw = self._r.hget(self._k("job", job_id), "data")
        if not raw:
            return None
        return QueueJob.from_dict(json.loads(raw))

    def _save(self, job: QueueJob) -> None:
        job.updated_at = time.time()
        self._r.hset(self._k("job", job.id), mapping={"data": json.dumps(job.to_dict())})

    def claim(self, queue: str, *, worker_id: str, timeout: int = 5) -> QueueJob | None:
        """Blocking move from queue → processing list."""
        src = self._k("queue", queue)
        dst = self._k("processing", queue)
        job_id = self._r.brpoplpush(src, dst, timeout=timeout)
        if not job_id:
            return None
        job = self.get(str(job_id))
        if job is None:
            self._r.lrem(dst, 1, job_id)
            return None
        now = time.time()
        if job.available_at > now:
            # Not ready yet — put back and skip briefly.
            self._r.lrem(dst, 1, job_id)
            self._r.lpush(src, job_id)
            time.sleep(0.05)
            return None
        job.status = "processing"
        job.attempts += 1
        self._save(job)
        self._r.set(self._k("lease", job.id), worker_id, ex=max(30, job.timeout_seconds))
        return job

    def complete(self, job: QueueJob) -> None:
        job.status = "completed"
        self._save(job)
        self._r.lrem(self._k("processing", job.queue), 1, job.id)
        self._r.delete(self._k("lease", job.id))

    def requeue_soft(self, job: QueueJob, *, delay_seconds: float = 1.0) -> None:
        """Put job back without counting a hard failure (tenant concurrency / not ready)."""
        processing = self._k("processing", job.queue)
        self._r.lrem(processing, 1, job.id)
        self._r.delete(self._k("lease", job.id))
        # Undo claim attempt increment for soft requeue.
        job.attempts = max(0, job.attempts - 1)
        job.status = "queued"
        job.available_at = time.time() + max(0.05, delay_seconds)
        self._save(job)
        self._r.lpush(self._k("queue", job.queue), job.id)

    def fail(self, job: QueueJob, *, error: str, retry: bool) -> bool:
        """Return True when job entered DLQ (dead)."""
        job.last_error = error[:1000]
        processing = self._k("processing", job.queue)
        self._r.lrem(processing, 1, job.id)
        self._r.delete(self._k("lease", job.id))
        if retry and job.attempts < (job.max_attempts or DEFAULT_MAX_ATTEMPTS):
            # Exponential backoff: 2^attempts seconds (capped).
            delay = min(300, 2 ** min(job.attempts, 8))
            job.status = "queued"
            job.available_at = time.time() + delay
            self._save(job)
            self._r.lpush(self._k("queue", job.queue), job.id)
            return False
        job.status = "dead"
        self._save(job)
        self._r.lpush(self._k("dlq", job.queue), job.id)
        return True

    def throttle_provider(self, *, provider: str, limit_per_minute: int) -> bool:
        """Fixed-window provider throttle. True = allowed."""
        if limit_per_minute <= 0:
            return True
        key = self._k("throttle", provider, str(int(time.time() // 60)))
        count = int(self._r.incr(key))
        if count == 1:
            self._r.expire(key, 120)
        return count <= limit_per_minute

    def depth(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name in QUEUE_NAMES:
            out[name] = int(self._r.llen(self._k("queue", name)) or 0)
            out[f"{name}_processing"] = int(self._r.llen(self._k("processing", name)) or 0)
            out[f"{name}_dlq"] = int(self._r.llen(self._k("dlq", name)) or 0)
        return out

    def heartbeat(self, *, worker_id: str, queue: str) -> None:
        self._r.set(
            self._k("heartbeat", queue, worker_id),
            str(time.time()),
            ex=HEARTBEAT_TTL_SECONDS,
        )

    def heartbeats(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {q: [] for q in QUEUE_NAMES}
        for name in QUEUE_NAMES:
            pattern = self._k("heartbeat", name, "*")
            for key in self._r.scan_iter(match=pattern, count=100):
                out[name].append(str(key).rsplit(":", 1)[-1])
        return out

    def ping(self) -> bool:
        return bool(self._r.ping())

    def tenant_inflight(self, tenant_id: str) -> int:
        key = self._k("tenant_inflight", tenant_id)
        return int(self._r.get(key) or 0)

    def incr_tenant_inflight(self, tenant_id: str) -> int:
        key = self._k("tenant_inflight", tenant_id)
        val = int(self._r.incr(key))
        self._r.expire(key, 3600)
        return val

    def decr_tenant_inflight(self, tenant_id: str) -> None:
        key = self._k("tenant_inflight", tenant_id)
        try:
            self._r.decr(key)
        except Exception:
            pass
