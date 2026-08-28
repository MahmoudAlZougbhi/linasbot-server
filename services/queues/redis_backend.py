"""Redis-backed durable queue (lists + hash job store + delayed ZSET + DLQ)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from services.queues.config import (
    DEFAULT_MAX_ATTEMPTS,
    HEARTBEAT_TTL_SECONDS,
    QUEUE_NAMES,
    key_prefix,
    lease_ttl_seconds,
    redis_url,
)
from services.queues.claim_activate import job_id_text, set_claim_lease
from services.queues.job_lease import JobLease, lease_log, parse_removed
from services.queues.models import QueueJob
from services.queues.reclaim_scan import reclaim_expired_leases as scan_expired_leases
from services.scale.metrics import incr


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
        self._lease_ops = JobLease(self._r, key_prefix())

    def _lease(self) -> JobLease:
        return self._lease_ops

    def _k(self, *parts: str) -> str:
        return ":".join((key_prefix(), *parts))

    def _job_fields(self, job: QueueJob) -> dict[str, str]:
        return {
            "data": json.dumps(job.to_dict()),
            "status": str(job.status),
            "lease_token": str(job.lease_token or ""),
            "lease_owner": str(job.lease_owner or ""),
        }

    def _trace_id(self, job: QueueJob) -> str:
        payload = job.payload or {}
        return str(payload.get("trace_id") or payload.get("_trace_id") or "")

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
        pipe.hset(self._k("job", job.id), mapping=self._job_fields(job))
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
        self._r.hset(self._k("job", job.id), mapping=self._job_fields(job))
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
        job_id = self._r.brpoplpush(self._k("queue", queue), self._k("processing", queue), timeout=timeout)
        return self._bind_claimed(queue, job_id, worker_id=worker_id)

    def try_claim(self, queue: str, *, worker_id: str) -> QueueJob | None:
        """Non-blocking claim for isolated replica pools and tests."""
        self._promote_ready(queue)
        job_id = self._r.rpoplpush(self._k("queue", queue), self._k("processing", queue))
        return self._bind_claimed(queue, job_id, worker_id=worker_id)

    def _bind_claimed(self, queue: str, job_id: Any, *, worker_id: str) -> QueueJob | None:
        jid = job_id_text(job_id)
        if not jid:
            return None
        owner = str(worker_id)
        token = uuid.uuid4().hex
        wire = QueueJob.wire_for(owner, token)
        set_claim_lease(
            self._r,
            job_id=jid,
            lease_prefix=f"{key_prefix()}:lease:",
            wire=wire,
            ttl_seconds=self._lease_ttl(),
        )
        try:
            return self._activate_claimed(queue, jid, owner=owner, token=token)
        except Exception:
            self._r.delete(self._k("lease", jid))
            self._r.lrem(self._k("processing", queue), 1, jid)
            self._r.lpush(self._k("queue", queue), jid)
            raise

    def _activate_claimed(self, queue: str, job_id: Any, *, owner: str, token: str) -> QueueJob | None:
        jid = str(job_id or "")
        if not jid:
            return None
        dst = self._k("processing", queue)
        lease_key = self._k("lease", jid)

        def _abort() -> None:
            self._r.delete(lease_key)
            self._r.lrem(dst, 1, jid)

        job = self.get(jid)
        if job is None:
            _abort()
            return None
        if job.status in {"completed", "dead"}:
            _abort()
            return None
        now = time.time()
        if job.available_at > now:
            _abort()
            self._r.zadd(self._k("delayed", queue), {job.id: job.available_at})
            return None
        job.status = "processing"
        job.attempts += 1
        job.lease_owner = owner
        job.lease_token = token
        job.updated_at = now
        self._save(job)
        self._unmark_waiting(job)
        self._r.expire(lease_key, self._lease_ttl())
        return job

    def _lease_ttl(self) -> int:
        return int(lease_ttl_seconds())

    def refresh_lease(self, job_id: str, worker_id: str, lease_token: str = "") -> bool:
        token = str(lease_token or "").strip()
        owner = str(worker_id or "").strip()
        if not token or not owner:
            return False
        return self._lease().refresh(
            job_id=str(job_id),
            wire=QueueJob.wire_for(owner, token),
            ttl_seconds=self._lease_ttl(),
        )

    def reclaim_expired_leases(self, queue: str, *, limit: int = 50) -> int:
        """Requeue jobs whose worker died (lease key gone). Long jobs with a live heartbeat stay owned."""
        return scan_expired_leases(self, queue, limit=limit)

    def complete(self, job: QueueJob) -> str:

        payload = dict(job.to_dict())
        payload["status"] = "completed"
        payload["lease_token"] = ""
        payload["lease_owner"] = ""
        payload["updated_at"] = time.time()
        result = self._lease().complete(
            queue=job.queue,
            job_id=job.id,
            token=str(job.lease_token or ""),
            wire=job.lease_wire(),
            data_json=json.dumps(payload),
        )
        trace_id = self._trace_id(job)
        if result.startswith("already_completed") or result.startswith("ok"):
            removed = parse_removed(result)
            if removed:
                incr("completed_removed_from_dlq", float(removed))
            job.status = "completed"
            job.lease_token = ""
            job.lease_owner = ""
            try:
                from services.scale.job_progress import clear_progress

                clear_progress(job.id, redis_client=self._r)
            except Exception:
                pass
            lease_log("complete", job_id=job.id, trace_id=trace_id, extra=result)
            return result
        if result == "stale_owner":
            incr("stale_owner_complete_attempt")
            lease_log("stale_owner_complete", job_id=job.id, trace_id=trace_id)
        else:
            lease_log("complete_rejected", job_id=job.id, trace_id=trace_id, extra=result)
        return result

    def requeue_soft(self, job: QueueJob, *, delay_seconds: float = 1.0) -> None:
        now = time.time()
        job.attempts = max(0, job.attempts - 1)
        job.status = "queued"
        job.available_at = now + max(0.05, delay_seconds)
        payload = dict(job.to_dict())
        payload["lease_token"] = ""
        payload["lease_owner"] = ""
        result = self._lease().requeue_soft(
            queue=job.queue,
            job_id=job.id,
            token=str(job.lease_token or ""),
            wire=job.lease_wire(),
            data_json=json.dumps(payload),
            available_at=float(job.available_at),
            now=now,
            waiting_score=float(job.created_at),
        )
        if result == "ok":
            job.lease_token = ""
            job.lease_owner = ""

    def fail(self, job: QueueJob, *, error: str, retry: bool) -> bool:
        stored = self.get(job.id)
        if stored is not None and stored.status in {"completed", "dead"}:
            return stored.status == "dead"
        if job.status in {"completed", "dead"}:
            return job.status == "dead"
        now = time.time()
        go_dead = not (retry and job.attempts < (job.max_attempts or DEFAULT_MAX_ATTEMPTS))
        payload = dict(job.to_dict())
        payload["last_error"] = error[:1000]
        payload["lease_token"] = ""
        payload["lease_owner"] = ""
        if go_dead:
            payload["status"] = "dead"
            available_at = now
        else:
            from services.scale.retry_backoff import retry_delay_seconds

            delay = retry_delay_seconds(attempts=job.attempts, error=error)
            payload["status"] = "queued"
            payload["available_at"] = now + delay
            available_at = float(payload["available_at"])
        result = self._lease().fail(
            queue=job.queue,
            job_id=job.id,
            token=str(job.lease_token or ""),
            wire=job.lease_wire(),
            data_json=json.dumps(payload),
            terminal_status="dead" if go_dead else "queued",
            available_at=available_at,
            now=now,
            waiting_score=float(job.created_at),
        )
        if result == "stale_owner":
            from services.scale.metrics import incr

            incr("stale_owner_complete_attempt")
            lease_log("stale_owner_fail", job_id=job.id, trace_id=self._trace_id(job))
            return False
        if result in {"already_completed", "already_dead", "not_processing"}:
            return result == "already_dead"
        if result == "dead":
            job.status = "dead"
            job.last_error = error[:1000]
            job.lease_token = ""
            job.lease_owner = ""
            self._record_dead(job, error=error)
            return True
        if result == "retried":
            job.status = "queued"
            job.last_error = error[:1000]
            job.available_at = available_at
            job.lease_token = ""
            job.lease_owner = ""
            return False
        return False

    def _record_dead(self, job: QueueJob, *, error: str) -> None:
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
