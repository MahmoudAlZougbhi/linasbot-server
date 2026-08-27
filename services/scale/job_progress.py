"""Per-job progress record: stage + last_progress_at. Distinct from worker liveness."""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass
from typing import Any

from services.queues.config import key_prefix

_TEST_CLIENT: Any | None = None
_bind: contextvars.ContextVar[JobProgressBind | None] = contextvars.ContextVar(
    "linas_job_progress_bind",
    default=None,
)


@dataclass(frozen=True)
class JobProgressBind:
    job_id: str
    worker_id: str
    lease_token: str
    attempt: int
    trace_id: str
    redis: Any


@dataclass
class JobProgress:
    job_id: str
    current_stage: str
    stage_started_at: float
    last_progress_at: float
    worker_id: str
    lease_token: str
    attempt: int
    trace_id: str
    stuck_count: int = 0
    timeout_count: int = 0
    last_stuck_stage: str = ""
    last_error: str = ""
    abort: bool = False


def set_progress_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client(explicit: Any | None = None) -> Any | None:
    if explicit is not None:
        return explicit
    bound = _bind.get()
    if bound is not None and bound.redis is not None:
        return bound.redis
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def _key(job_id: str) -> str:
    return f"{key_prefix()}:prog:{job_id}"


def bind_job(job: Any, *, redis: Any, worker_id: str) -> JobProgressBind:
    payload = getattr(job, "payload", None) or {}
    record = JobProgressBind(
        job_id=str(job.id),
        worker_id=str(worker_id),
        lease_token=str(getattr(job, "lease_token", "") or ""),
        attempt=int(getattr(job, "attempts", 0) or 0),
        trace_id=str(payload.get("trace_id") or payload.get("_trace_id") or ""),
        redis=redis,
    )
    _bind.set(record)
    return record


def unbind_job() -> None:
    _bind.set(None)


def current_bind() -> JobProgressBind | None:
    return _bind.get()


def heartbeat_should_stop(job_id: str, token: str, *, redis_client: Any | None = None) -> bool:
    client = _client(redis_client)
    if client is None or not job_id:
        return False
    raw = client.hgetall(_key(job_id)) or {}
    if str(raw.get("abort") or "") in {"1", "true"}:
        return True
    stored = str(raw.get("lease_token") or "")
    if stored and token and stored != token:
        return True
    return False


def mark_stage(stage: str, *, job_id: str | None = None, redis_client: Any | None = None) -> bool:
    bound = _bind.get()
    jid = str(job_id or (bound.job_id if bound else "") or "").strip()
    if not jid or not stage:
        return False
    client = _client(redis_client if redis_client is not None else (bound.redis if bound else None))
    if client is None:
        return False
    now = time.time()
    key = _key(jid)
    raw = client.hgetall(key) or {}
    if str(raw.get("abort") or "") in {"1", "true"}:
        return False
    token = str((bound.lease_token if bound else "") or raw.get("lease_token") or "")
    stored_token = str(raw.get("lease_token") or "")
    if stored_token and token and stored_token != token:
        return False
    prev_stage = str(raw.get("current_stage") or "")
    stage_started = str(now) if prev_stage != stage else str(raw.get("stage_started_at") or now)
    mapping = {
        "job_id": jid,
        "current_stage": stage,
        "stage_started_at": stage_started,
        "last_progress_at": str(now),
        "worker_id": str((bound.worker_id if bound else "") or raw.get("worker_id") or ""),
        "lease_token": token or stored_token,
        "attempt": str((bound.attempt if bound else "") or raw.get("attempt") or "0"),
        "trace_id": str((bound.trace_id if bound else "") or raw.get("trace_id") or ""),
        "stuck_count": str(raw.get("stuck_count") or "0"),
        "timeout_count": str(raw.get("timeout_count") or "0"),
        "last_stuck_stage": str(raw.get("last_stuck_stage") or ""),
        "last_error": str(raw.get("last_error") or ""),
        "abort": "0",
    }
    client.hset(key, mapping=mapping)
    client.expire(key, 60 * 60 * 24)
    return True


def load_progress(job_id: str, *, redis_client: Any | None = None) -> JobProgress | None:
    client = _client(redis_client)
    if client is None or not job_id:
        return None
    raw = client.hgetall(_key(job_id)) or {}
    if not raw:
        return None

    def _f(name: str, default: float = 0.0) -> float:
        try:
            return float(raw.get(name) or default)
        except (TypeError, ValueError):
            return default

    def _i(name: str) -> int:
        try:
            return int(raw.get(name) or 0)
        except (TypeError, ValueError):
            return 0

    return JobProgress(
        job_id=str(raw.get("job_id") or job_id),
        current_stage=str(raw.get("current_stage") or "processing"),
        stage_started_at=_f("stage_started_at"),
        last_progress_at=_f("last_progress_at"),
        worker_id=str(raw.get("worker_id") or ""),
        lease_token=str(raw.get("lease_token") or ""),
        attempt=_i("attempt"),
        trace_id=str(raw.get("trace_id") or ""),
        stuck_count=_i("stuck_count"),
        timeout_count=_i("timeout_count"),
        last_stuck_stage=str(raw.get("last_stuck_stage") or ""),
        last_error=str(raw.get("last_error") or ""),
        abort=str(raw.get("abort") or "") in {"1", "true"},
    )


def set_abort(
    job_id: str,
    *,
    redis_client: Any,
    stuck_stage: str,
    error: str,
    stuck_count: int,
    timeout_count: int,
    lease_token: str,
) -> None:
    key = _key(job_id)
    client = redis_client
    client.hset(
        key,
        mapping={
            "abort": "1",
            "last_stuck_stage": stuck_stage,
            "last_error": error[:500],
            "stuck_count": str(stuck_count),
            "timeout_count": str(timeout_count),
            "lease_token": lease_token,
        },
    )


def clear_progress(job_id: str, *, redis_client: Any | None = None) -> None:
    client = _client(redis_client)
    if client is None or not job_id:
        return
    try:
        client.delete(_key(job_id))
    except Exception:
        return
