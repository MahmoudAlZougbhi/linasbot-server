"""Detect in-flight jobs that are alive-but-stuck. Dead workers use lease reclaim, not this path."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from services.queues.config import DEFAULT_MAX_ATTEMPTS, lease_ttl_seconds
from services.scale.job_progress import JobProgress, clear_progress, load_progress, set_abort
from services.scale.job_progress_policy import grace_seconds, max_stuck_count, stage_timeout_seconds
from services.scale.metrics import incr, set_gauge

_log = logging.getLogger("uvicorn.error")
WATCHDOG_OWNER = "progress-watchdog"


@dataclass(frozen=True)
class StuckVerdict:
    kind: str
    stage: str
    last_progress_age: float
    heartbeat_age: float
    timeout_seconds: float


def classify_progress(
    *,
    lease_exists: bool,
    status: str,
    progress: JobProgress | None,
    now: float,
    last_progress_at: float,
    stage: str,
) -> StuckVerdict:
    if status in {"completed", "dead"}:
        return StuckVerdict("ignore_terminal", stage or "completed", 0.0, 0.0, 0.0)
    age = max(0.0, now - float(last_progress_at or 0.0))
    timeout = stage_timeout_seconds(stage)
    grace = grace_seconds()
    hb_age = 0.0
    if progress is not None:
        hb_age = max(0.0, now - float(progress.last_progress_at or 0.0))
    if not lease_exists:
        return StuckVerdict("dead_worker", stage, age, hb_age, timeout)
    if age <= timeout:
        return StuckVerdict("healthy", stage, age, hb_age, timeout)
    if age <= timeout + grace:
        return StuckVerdict("false_stuck_prevented", stage, age, hb_age, timeout)
    return StuckVerdict("stuck", stage, age, hb_age, timeout)


def _trace_of(job: Any, progress: JobProgress | None) -> str:
    payload = getattr(job, "payload", None) or {}
    if progress and progress.trace_id:
        return progress.trace_id
    return str(payload.get("trace_id") or payload.get("_trace_id") or "")


def _delivery_key(job: Any) -> str:
    payload = getattr(job, "payload", None) or {}
    return str(
        payload.get("_logical_reply_id") or payload.get("logical_reply_id") or payload.get("_inbound_event_id") or ""
    ).strip()


def _has_saved_ai(job: Any) -> bool:
    payload = getattr(job, "payload", None) or {}
    lid = _delivery_key(job)
    basis = str(payload.get("_claim_key_basis") or payload.get("claim_key_basis") or "").strip()
    try:
        from services.ai_reply_lifecycle import find_pending_delivery_turn, get_turn

        if lid:
            rec = get_turn(lid)
            if rec is not None and rec.generated_reply:
                return True
        if basis:
            pending = find_pending_delivery_turn(claim_key_basis=basis)
            if pending is not None and pending.generated_reply:
                return True
    except Exception:
        return False
    return False


def scan_queue(backend: Any, queue: str, *, limit: int = 50) -> dict[str, int]:
    """Inspect processing jobs. Lease missing → leave to reclaim. Lease present + stale → stuck."""
    stats = {"scanned": 0, "stuck": 0, "recovered": 0, "dlq": 0, "false_prevented": 0}
    processing = backend._k("processing", queue)
    job_ids = backend._r.lrange(processing, 0, max(0, limit - 1)) or []
    now = time.time()
    for job_id in job_ids:
        stats["scanned"] += 1
        lease_exists = bool(backend._r.exists(backend._k("lease", str(job_id))))
        job = backend.get(str(job_id))
        if job is None:
            continue
        progress = load_progress(str(job_id), redis_client=backend._r)
        stage = progress.current_stage if progress else "processing"
        last_at = progress.last_progress_at if progress else float(getattr(job, "updated_at", now) or now)
        verdict = classify_progress(
            lease_exists=lease_exists,
            status=str(job.status),
            progress=progress,
            now=now,
            last_progress_at=last_at,
            stage=stage,
        )
        set_gauge("last_progress_age", verdict.last_progress_age)
        set_gauge("heartbeat_age", verdict.heartbeat_age)
        if verdict.kind == "ignore_terminal":
            continue
        if verdict.kind == "dead_worker":
            continue
        if verdict.kind == "healthy":
            continue
        if verdict.kind == "false_stuck_prevented":
            incr("false_stuck_prevented")
            stats["false_prevented"] += 1
            continue
        recovered = _recover_stuck(backend, job, progress, verdict)
        stats["stuck"] += 1
        if recovered == "dlq":
            stats["dlq"] += 1
        elif recovered == "retry":
            stats["recovered"] += 1
    return stats


def _recover_stuck(backend: Any, job: Any, progress: JobProgress | None, verdict: StuckVerdict) -> str:
    incr("job_stuck_detected")
    incr("stage_timeout")
    if verdict.stage in {"luna_started", "tera_started"}:
        incr("provider_timeout")
    set_gauge("stuck_stage", float(len(verdict.stage)))
    started = progress.stage_started_at if progress else float(job.updated_at)
    set_gauge("recovery_duration", max(0.0, time.time() - started))
    trace_id = _trace_of(job, progress)
    stuck_count = int(progress.stuck_count if progress else 0) + 1
    timeout_count = int(progress.timeout_count if progress else 0) + 1
    expected_token = str(job.lease_token or (progress.lease_token if progress else "") or "")
    expected_wire = job.lease_wire()
    new_token = uuid.uuid4().hex
    new_wire = job.wire_for(WATCHDOG_OWNER, new_token)
    previous_owner = str(job.lease_owner or "")
    previous_token = str(job.lease_token or "")
    job.lease_owner = WATCHDOG_OWNER
    job.lease_token = new_token
    import json

    data_json = json.dumps(job.to_dict())
    result = backend._lease().takeover(
        queue=job.queue,
        job_id=job.id,
        expected_token=expected_token,
        expected_wire=expected_wire,
        new_token=new_token,
        new_owner=WATCHDOG_OWNER,
        data_json=data_json,
        new_wire=new_wire,
        ttl_seconds=lease_ttl_seconds(),
    )
    if result != "ok":
        job.lease_owner = previous_owner
        job.lease_token = previous_token
        _log.info(
            "[progress] takeover_skipped job_id=%s trace_id=%s result=%s stage=%s",
            job.id,
            trace_id or "-",
            result,
            verdict.stage,
        )
        return "skipped"
    set_abort(
        job.id,
        redis_client=backend._r,
        stuck_stage=verdict.stage,
        error=f"stuck:{verdict.stage}",
        stuck_count=stuck_count,
        timeout_count=timeout_count,
        lease_token=new_token,
    )
    _log.info(
        "[progress] stuck job_id=%s trace_id=%s stage=%s stuck_count=%s",
        job.id,
        trace_id or "-",
        verdict.stage,
        stuck_count,
    )
    if verdict.stage == "delivery_started":
        key = _delivery_key(job)
        if key:
            try:
                from services.scale.delivery_ledger import mark_unknown

                mark_unknown(key)
            except Exception:
                pass
    if stuck_count >= max_stuck_count() or job.attempts >= (job.max_attempts or DEFAULT_MAX_ATTEMPTS):
        went_dead = backend.fail(job, error=f"stuck:{verdict.stage}", retry=False)
        incr("job_stuck_dlq")
        clear_progress(job.id, redis_client=backend._r)
        return "dlq" if went_dead else "skipped"
    error = f"stuck:{verdict.stage}"
    if _has_saved_ai(job):
        error = f"stuck:{verdict.stage}:resume_saved_ai"
    backend.fail(job, error=error, retry=True)
    incr("job_stuck_recovered")
    return "retry"
