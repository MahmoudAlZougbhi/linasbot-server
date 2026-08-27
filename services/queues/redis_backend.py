"""Redis-backed durable queue (lists + hash job store + delayed ZSET + DLQ)."""

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
    from services.scale.redis_pool import redis_client

    pooled = redis_client()
    if pooled is not None:
        return pooled
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


class RedisQueueBackend:
    def __init__(self) -> None:
        self._r = _client()
        self.backend = "redis"
        self.production_ready = True

    def _k(self, *parts: str) -> str:
        return ":".join((key_prefix(), *parts))

    def _idem_key(self, queue: str, tenant_id: str, idempotency_key: str) -> str:
        return self._k("idem", queue, tenant_id, idempotency_key)

    def get_by_idempotency(self, queue: str, tenant_id: str, idempotency_key: str) -> QueueJob | None:
        existing = self._r.get(self._idem_key(queue, tenant_id, idempotency_key))
        if not existing:
            return None
        return self.get(str(existing))

    def clear_idempotency(self, queue: str, tenant_id: str, idempotency_key: str) -> None:
        self._r.delete(self._idem_key(queue, tenant_id, idempotency_key))

    def _park(self, job: QueueJob) -> None:
        delayed = self._k("delayed", job.queue)
        src = self._k("queue", job.queue)
        now = time.time()
        self._r.lrem(src, 0, job.id)
        if job.available_at > now:
            self._r.zadd(delayed, {job.id: job.available_at})
        else:
            self._r.zrem(delayed, job.id)
            self._r.lpush(src, job.id)

    def set_available_at(self, job: QueueJob, available_at: float) -> None:
        job.available_at = float(available_at)
        if job.status == "queued":
            self._save(job)
            self._park(job)
            return
        self._save(job)

    def _mark_waiting(self, job: QueueJob) -> None:
        self._r.zadd(self._k("waiting", job.queue), {job.id: float(job.created_at)})

    def _unmark_waiting(self, job: QueueJob) -> None:
        self._r.zrem(self._k("waiting", job.queue), job.id)

    def enqueue(self, job: QueueJob) -> QueueJob:
        if job.idempotency_key:
            found = self.get_by_idempotency(job.queue, job.tenant_id, job.idempotency_key)
            if found is not None:
                return found
        now = time.time()
        pipe = self._r.pipeline()
        pipe.hset(self._k("job", job.id), mapping={"data": json.dumps(job.to_dict())})
        if job.available_at > now:
            pipe.zadd(self._k("delayed", job.queue), {job.id: job.available_at})
        else:
            pipe.lpush(self._k("queue", job.queue), job.id)
        pipe.zadd(self._k("waiting", job.queue), {job.id: float(job.created_at)})
        if job.idempotency_key:
            pipe.set(self._idem_key(job.queue, job.tenant_id, job.idempotency_key), job.id, ex=60 * 60 * 24 * 7)
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
        delayed = self._k("delayed", job.queue)
        if self._r.zscore(delayed, job.id) is not None:
            self._r.zadd(delayed, {job.id: job.available_at})

    def _promote_ready(self, queue: str) -> None:
        delayed = self._k("delayed", queue)
        now = time.time()
        ready = self._r.zrangebyscore(delayed, "-inf", now, start=0, num=100)
        src = self._k("queue", queue)
        for job_id in ready or []:
            job = self.get(str(job_id))
            if job is None:
                self._r.zrem(delayed, job_id)
                continue
            if job.available_at > now:
                self._r.zadd(delayed, {job_id: job.available_at})
                continue
            pipe = self._r.pipeline()
            pipe.zrem(delayed, job_id)
            pipe.lpush(src, job_id)
            pipe.execute()

    def claim(self, queue: str, *, worker_id: str, timeout: int = 5) -> QueueJob | None:
        """Move one ready job from queue → processing. Delayed jobs stay in a ZSET."""
        self._promote_ready(queue)
        src = self._k("queue", queue)
        dst = self._k("processing", queue)
        job_id = self._r.brpoplpush(src, dst, timeout=timeout)
        return self._activate_claimed(queue, job_id, worker_id=worker_id)

    def try_claim(self, queue: str, *, worker_id: str) -> QueueJob | None:
        """Non-blocking claim for isolated replica pools and tests."""
        self._promote_ready(queue)
        src = self._k("queue", queue)
        dst = self._k("processing", queue)
        job_id = self._r.rpoplpush(src, dst)
        return self._activate_claimed(queue, job_id, worker_id=worker_id)

    def _activate_claimed(self, queue: str, job_id: Any, *, worker_id: str) -> QueueJob | None:
        if not job_id:
            return None
        dst = self._k("processing", queue)
        job = self.get(str(job_id))
        if job is None:
            self._r.lrem(dst, 1, job_id)
            return None
        if job.status in {"completed", "dead"}:
            self._r.lrem(dst, 1, job_id)
            return None
        now = time.time()
        if job.available_at > now:
            self._r.lrem(dst, 1, job_id)
            self._r.zadd(self._k("delayed", queue), {job.id: job.available_at})
            return None
        job.status = "processing"
        job.attempts += 1
        self._save(job)
        self._unmark_waiting(job)
        self._r.set(self._k("lease", job.id), worker_id, ex=self._lease_ttl())
        return job

    def _lease_ttl(self) -> int:
        return max(15, HEARTBEAT_TTL_SECONDS * 2)

    def refresh_lease(self, job_id: str, worker_id: str) -> bool:
        key = self._k("lease", job_id)
        current = self._r.get(key)
        if str(current or "") != str(worker_id):
            return False
        self._r.expire(key, self._lease_ttl())
        return True

    def reclaim_expired_leases(self, queue: str, *, limit: int = 50) -> int:
        """Requeue jobs whose worker died (lease key gone) so work is not lost."""
        processing = self._k("processing", queue)
        job_ids = self._r.lrange(processing, 0, max(0, limit - 1)) or []
        reclaimed = 0
        for job_id in job_ids:
            if self._r.exists(self._k("lease", str(job_id))):
                continue
            job = self.get(str(job_id))
            if job is None or job.status in {"completed", "dead"}:
                self._r.lrem(processing, 1, job_id)
                continue
            if job.attempts >= (job.max_attempts or DEFAULT_MAX_ATTEMPTS):
                self.fail(job, error="lease_expired", retry=False)
                reclaimed += 1
                continue
            self._r.lrem(processing, 1, job_id)
            self._r.delete(self._k("lease", str(job_id)))
            job.status = "queued"
            job.available_at = time.time()
            job.last_error = "lease_expired"
            self._save(job)
            self._mark_waiting(job)
            self._park(job)
            reclaimed += 1
        return reclaimed

    def complete(self, job: QueueJob) -> None:
        job.status = "completed"
        self._save(job)
        self._r.lrem(self._k("processing", job.queue), 1, job.id)
        self._r.lrem(self._k("queue", job.queue), 0, job.id)
        self._r.zrem(self._k("delayed", job.queue), job.id)
        self._r.delete(self._k("lease", job.id))
        self._unmark_waiting(job)

    def requeue_soft(self, job: QueueJob, *, delay_seconds: float = 1.0) -> None:
        processing = self._k("processing", job.queue)
        self._r.lrem(processing, 1, job.id)
        self._r.delete(self._k("lease", job.id))
        job.attempts = max(0, job.attempts - 1)
        job.status = "queued"
        job.available_at = time.time() + max(0.05, delay_seconds)
        self._save(job)
        self._mark_waiting(job)
        self._park(job)

    def fail(self, job: QueueJob, *, error: str, retry: bool) -> bool:
        stored = self.get(job.id)
        if stored is not None and stored.status in {"completed", "dead"}:
            return stored.status == "dead"
        if job.status in {"completed", "dead"}:
            return job.status == "dead"
        job.last_error = error[:1000]
        processing = self._k("processing", job.queue)
        self._r.lrem(processing, 1, job.id)
        self._r.delete(self._k("lease", job.id))
        if retry and job.attempts < (job.max_attempts or DEFAULT_MAX_ATTEMPTS):
            from services.scale.retry_backoff import retry_delay_seconds

            delay = retry_delay_seconds(attempts=job.attempts, error=error)
            job.status = "queued"
            job.available_at = time.time() + delay
            self._save(job)
            self._mark_waiting(job)
            self._park(job)
            return False
        job.status = "dead"
        self._save(job)
        self._r.lpush(self._k("dlq", job.queue), job.id)
        self._unmark_waiting(job)
        try:
            from services.scale.dlq_record import record_dead

            record_dead(
                job_id=job.id,
                job_type=job.job_type,
                tenant_id=job.tenant_id,
                error=error,
                attempts=int(job.attempts),
                conversation_key=str((job.payload or {}).get("_conversation_key") or ""),
                channel=str((job.payload or {}).get("channel") or ""),
                created_at=float(job.created_at),
            )
        except Exception:
            pass
        return True

    def throttle_provider(self, *, provider: str, limit_per_minute: int) -> bool:
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
            out[f"{name}_delayed"] = int(self._r.zcard(self._k("delayed", name)) or 0)
        return out

    def oldest_age_seconds(self, queue: str) -> float:
        first = self._r.zrange(self._k("waiting", queue), 0, 0, withscores=True)
        if not first:
            return 0.0
        return max(0.0, time.time() - float(first[0][1]))

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
        return int(self._r.get(self._k("tenant_inflight", tenant_id)) or 0)

    def incr_tenant_inflight(self, tenant_id: str) -> int:
        key = self._k("tenant_inflight", tenant_id)
        val = int(self._r.incr(key))
        self._r.expire(key, 3600)
        return val

    def decr_tenant_inflight(self, tenant_id: str) -> None:
        try:
            self._r.decr(self._k("tenant_inflight", tenant_id))
        except Exception:
            pass
