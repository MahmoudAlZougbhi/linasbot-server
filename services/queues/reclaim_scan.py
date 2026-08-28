"""Scan processing jobs whose worker died (lease key gone)."""

from __future__ import annotations

import json
import time
from typing import Any

from services.queues.config import DEFAULT_MAX_ATTEMPTS
from services.queues.job_lease import lease_log, parse_removed
from services.scale.metrics import incr


def reclaim_expired_leases(backend: Any, queue: str, *, limit: int = 50) -> int:
    """Requeue jobs whose worker died. Live claims keep a lease key and are skipped."""

    processing = backend._k("processing", queue)
    job_ids = backend._r.lrange(processing, 0, max(0, limit - 1)) or []
    reclaimed = 0
    now = time.time()
    for job_id in job_ids:
        if backend._r.exists(backend._k("lease", str(job_id))):
            continue
        job = backend.get(str(job_id))
        if job is None:
            backend._r.lrem(processing, 1, job_id)
            continue
        if str(job.status) not in {"completed", "dead", "processing"}:
            result = backend._lease().reclaim(
                queue=queue,
                job_id=str(job_id),
                expected_token=str(job.lease_token or ""),
                data_json=json.dumps(job.to_dict()),
                next_status="queued",
                available_at=now,
                now=now,
                waiting_score=float(job.created_at),
            )
            if result == "pending_activate":
                lease_log("pending_activate", job_id=str(job_id), extra="returned_to_queue")
            continue
        expected_token = str(job.lease_token or "")
        if job.status not in {"completed", "dead"}:
            incr("lease_expired")
        next_status = "dead" if job.attempts >= (job.max_attempts or DEFAULT_MAX_ATTEMPTS) else "queued"
        if job.status in {"completed", "dead"}:
            next_status = str(job.status)
        payload = dict(job.to_dict())
        payload["lease_token"] = ""
        payload["lease_owner"] = ""
        if next_status == "queued":
            payload["status"] = "queued"
            payload["last_error"] = "lease_expired"
            payload["available_at"] = now
        elif next_status == "dead":
            payload["status"] = "dead"
            payload["last_error"] = "lease_expired"
        result = backend._lease().reclaim(
            queue=queue,
            job_id=str(job_id),
            expected_token=expected_token,
            data_json=json.dumps(payload),
            next_status=next_status if next_status in {"queued", "dead"} else str(job.status),
            available_at=float(payload.get("available_at") or now),
            now=now,
            waiting_score=float(job.created_at),
        )
        if result == "lost_race":
            incr("duplicate_reclaim_prevented")
            continue
        if result.startswith("terminal_completed"):
            removed = parse_removed(result)
            if removed:
                incr("completed_removed_from_dlq", float(removed))
            continue
        if result == "alive":
            continue
        if result == "pending_activate":
            continue
        if result in {"reclaimed", "dead", "terminal_dead"}:
            incr("lease_reclaimed")
            reclaimed += 1
            lease_log(
                "reclaimed" if result != "dead" else "lease_expired_dlq",
                job_id=str(job_id),
                trace_id=backend._trace_id(job),
                extra=f"result={result}",
            )
            if result == "dead":
                backend._record_dead(job, error="lease_expired")
    return reclaimed
