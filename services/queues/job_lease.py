"""Atomic Redis lease ownership. Lease is worker liveness, not a job duration cap.

Uses WATCH/MULTI/EXEC compare-and-set so two owners cannot both win. Lua is not
required: production Redis and fakeredis both implement transactions.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from redis.exceptions import WatchError

_log = logging.getLogger("uvicorn.error")
_OPS_LOCK = threading.RLock()


def lease_log(event: str, *, job_id: str, trace_id: str = "", extra: str = "") -> None:
    line = f"[lease] {event} job_id={job_id} trace_id={trace_id or '-'} {extra}"
    _log.info("%s", line)
    if event.startswith("heartbeat_") or event in {
        "reclaimed",
        "lease_expired_dlq",
        "stale_owner_complete",
        "stale_owner_fail",
    }:
        print(line, flush=True)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_removed(code: str) -> int:
    if ":" not in code:
        return 0
    try:
        return int(code.rsplit(":", 1)[-1])
    except ValueError:
        return 0


class JobLease:
    def __init__(self, redis_client: Any, prefix: str) -> None:
        self._r = redis_client
        self._prefix = prefix

    def _k(self, *parts: str) -> str:
        return ":".join((self._prefix, *parts))

    def _job_keys(self, queue: str, job_id: str) -> list[str]:
        return [
            self._k("job", job_id),
            self._k("lease", job_id),
            self._k("processing", queue),
            self._k("queue", queue),
            self._k("delayed", queue),
            self._k("dlq", queue),
            self._k("waiting", queue),
        ]

    def _txn(self, keys: list[str], body: Callable[[Any], str]) -> str:
        last = "error"
        with _OPS_LOCK:
            for _ in range(16):
                pipe = self._r.pipeline()
                try:
                    pipe.watch(*keys)
                    last = body(pipe)
                    return last
                except WatchError:
                    last = "lost_race"
                    continue
                finally:
                    try:
                        pipe.reset()
                    except Exception:
                        pass
        return last

    def refresh(self, *, job_id: str, wire: str, ttl_seconds: int) -> bool:
        if not wire:
            return False
        lease_key = self._k("lease", job_id)
        job_key = self._k("job", job_id)
        ttl = int(ttl_seconds)

        def body(pipe: Any) -> str:
            cur = _as_text(pipe.get(lease_key))
            if cur == wire:
                pipe.multi()
                pipe.expire(lease_key, ttl)
                pipe.execute()
                return "1"
            if cur:
                return "0"
            status = _as_text(pipe.hget(job_key, "status"))
            owner = _as_text(pipe.hget(job_key, "lease_owner")).strip()
            token = _as_text(pipe.hget(job_key, "lease_token")).strip()
            expected = f"{owner}::{token}" if owner and token else ""
            if status != "processing" or expected != wire:
                return "0"
            pipe.multi()
            pipe.set(lease_key, wire, ex=ttl)
            pipe.execute()
            return "1"

        return self._txn([lease_key, job_key], body) == "1"

    def complete(self, *, queue: str, job_id: str, token: str, wire: str, data_json: str) -> str:
        keys = self._job_keys(queue, job_id)
        job_key, lease_key = keys[0], keys[1]
        processing, queued, delayed, dlq, waiting = keys[2], keys[3], keys[4], keys[5], keys[6]

        def body(pipe: Any) -> str:
            status = str(pipe.hget(job_key, "status") or "")
            if status == "completed":
                pipe.multi()
                pipe.lrem(dlq, 0, job_id)
                pipe.lrem(processing, 0, job_id)
                pipe.lrem(queued, 0, job_id)
                pipe.zrem(delayed, job_id)
                pipe.delete(lease_key)
                pipe.zrem(waiting, job_id)
                removed = pipe.execute()
                n = int(removed[0] or 0) if removed else 0
                return f"already_completed:{n}"
            if status == "dead":
                return "already_dead"
            if status != "processing":
                return "not_processing"
            stored = str(pipe.hget(job_key, "lease_token") or "")
            if stored != token:
                return "stale_owner"
            lease = pipe.get(lease_key)
            if lease and str(lease) != wire:
                return "stale_owner"
            pipe.multi()
            pipe.hset(job_key, mapping={"data": data_json, "status": "completed", "lease_token": "", "lease_owner": ""})
            pipe.lrem(processing, 0, job_id)
            pipe.lrem(queued, 0, job_id)
            pipe.zrem(delayed, job_id)
            pipe.lrem(dlq, 0, job_id)
            pipe.delete(lease_key)
            pipe.zrem(waiting, job_id)
            executed = pipe.execute()
            n = int(executed[4] or 0) if executed else 0
            return f"ok:{n}"

        return self._txn([job_key, lease_key], body)

    def fail(
        self,
        *,
        queue: str,
        job_id: str,
        token: str,
        wire: str,
        data_json: str,
        terminal_status: str,
        available_at: float,
        now: float,
        waiting_score: float,
    ) -> str:
        keys = self._job_keys(queue, job_id)
        job_key, lease_key = keys[0], keys[1]
        processing, queued, delayed, dlq, waiting = keys[2], keys[3], keys[4], keys[5], keys[6]

        def body(pipe: Any) -> str:
            status = str(pipe.hget(job_key, "status") or "")
            if status == "completed":
                return "already_completed"
            if status == "dead":
                return "already_dead"
            if status != "processing":
                return "not_processing"
            stored = str(pipe.hget(job_key, "lease_token") or "")
            if stored != token:
                return "stale_owner"
            lease = pipe.get(lease_key)
            if lease and str(lease) != wire:
                return "stale_owner"
            pipe.multi()
            pipe.hset(
                job_key, mapping={"data": data_json, "status": terminal_status, "lease_token": "", "lease_owner": ""}
            )
            pipe.lrem(processing, 0, job_id)
            pipe.delete(lease_key)
            if terminal_status == "dead":
                pipe.lpush(dlq, job_id)
                pipe.zrem(waiting, job_id)
                pipe.zrem(delayed, job_id)
                pipe.lrem(queued, 0, job_id)
                pipe.execute()
                return "dead"
            if available_at > now:
                pipe.zadd(delayed, {job_id: available_at})
                pipe.lrem(queued, 0, job_id)
            else:
                pipe.zrem(delayed, job_id)
                pipe.lpush(queued, job_id)
            pipe.zadd(waiting, {job_id: waiting_score})
            pipe.execute()
            return "retried"

        return self._txn([job_key, lease_key], body)

    def reclaim(
        self,
        *,
        queue: str,
        job_id: str,
        expected_token: str,
        data_json: str,
        next_status: str,
        available_at: float,
        now: float,
        waiting_score: float,
    ) -> str:
        keys = self._job_keys(queue, job_id)
        job_key, lease_key = keys[0], keys[1]
        processing, queued, delayed, dlq, waiting = keys[2], keys[3], keys[4], keys[5], keys[6]

        def body(pipe: Any) -> str:
            if pipe.exists(lease_key):
                return "alive"
            status = str(pipe.hget(job_key, "status") or "")
            if status == "completed":
                pipe.multi()
                pipe.lrem(processing, 0, job_id)
                pipe.lrem(dlq, 0, job_id)
                pipe.lrem(queued, 0, job_id)
                pipe.zrem(delayed, job_id)
                pipe.zrem(waiting, job_id)
                removed = pipe.execute()
                n = int(removed[1] or 0) if removed else 0
                return f"terminal_completed:{n}"
            if status == "dead":
                pipe.multi()
                pipe.lrem(processing, 0, job_id)
                pipe.execute()
                return "terminal_dead"
            stored = str(pipe.hget(job_key, "lease_token") or "")
            if stored != expected_token:
                return "lost_race"
            if status != "processing":
                pipe.multi()
                pipe.lrem(processing, 0, job_id)
                pipe.execute()
                return "not_processing"
            pipe.multi()
            pipe.hset(job_key, mapping={"data": data_json, "status": next_status, "lease_token": "", "lease_owner": ""})
            pipe.lrem(processing, 0, job_id)
            if next_status == "dead":
                pipe.lpush(dlq, job_id)
                pipe.zrem(waiting, job_id)
                pipe.zrem(delayed, job_id)
                pipe.lrem(queued, 0, job_id)
                pipe.execute()
                return "dead"
            if available_at > now:
                pipe.zadd(delayed, {job_id: available_at})
                pipe.lrem(queued, 0, job_id)
            else:
                pipe.zrem(delayed, job_id)
                pipe.lpush(queued, job_id)
            pipe.zadd(waiting, {job_id: waiting_score})
            pipe.execute()
            return "reclaimed"

        return self._txn([job_key, lease_key], body)

    def takeover(
        self,
        *,
        queue: str,
        job_id: str,
        expected_token: str,
        expected_wire: str,
        new_token: str,
        new_owner: str,
        data_json: str,
        new_wire: str,
        ttl_seconds: int,
    ) -> str:
        job_key = self._k("job", job_id)
        lease_key = self._k("lease", job_id)

        def body(pipe: Any) -> str:
            status = str(pipe.hget(job_key, "status") or "")
            if status == "completed":
                return "already_completed"
            if status != "processing":
                return "not_processing"
            stored = str(pipe.hget(job_key, "lease_token") or "")
            if stored != expected_token:
                return "stale_owner"
            lease = pipe.get(lease_key)
            if (not lease) or str(lease) != expected_wire:
                return "stale_owner"
            pipe.multi()
            pipe.hset(
                job_key,
                mapping={
                    "data": data_json,
                    "status": "processing",
                    "lease_token": new_token,
                    "lease_owner": new_owner,
                },
            )
            pipe.set(lease_key, new_wire, ex=int(ttl_seconds))
            pipe.execute()
            return "ok"

        return self._txn([job_key, lease_key], body)

    def requeue_soft(
        self,
        *,
        queue: str,
        job_id: str,
        token: str,
        wire: str,
        data_json: str,
        available_at: float,
        now: float,
        waiting_score: float,
    ) -> str:
        keys = self._job_keys(queue, job_id)
        job_key, lease_key = keys[0], keys[1]
        processing, queued, delayed, waiting = keys[2], keys[3], keys[4], keys[6]

        def body(pipe: Any) -> str:
            status = str(pipe.hget(job_key, "status") or "")
            if status != "processing":
                return "not_processing"
            stored = str(pipe.hget(job_key, "lease_token") or "")
            if stored != token:
                return "stale_owner"
            lease = pipe.get(lease_key)
            if lease and str(lease) != wire:
                return "stale_owner"
            pipe.multi()
            pipe.hset(job_key, mapping={"data": data_json, "status": "queued", "lease_token": "", "lease_owner": ""})
            pipe.lrem(processing, 0, job_id)
            pipe.delete(lease_key)
            if available_at > now:
                pipe.zadd(delayed, {job_id: available_at})
                pipe.lrem(queued, 0, job_id)
            else:
                pipe.zrem(delayed, job_id)
                pipe.lpush(queued, job_id)
            pipe.zadd(waiting, {job_id: waiting_score})
            pipe.execute()
            return "ok"

        return self._txn([job_key, lease_key], body)
