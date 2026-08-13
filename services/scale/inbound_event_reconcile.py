"""Reconcile stuck durable inbound events (watchdog / restart recovery)."""

from __future__ import annotations

import logging
import time
from typing import Any

from services.queues.config import redis_required
from services.scale.inbound_event_store import (
    InboundEventRecord,
    accountability_stats,
    list_active_inbound_events,
    mark_inbound_state,
    put_inbound_event,
)

_runtime_logger = logging.getLogger("uvicorn.error")
_MAX_ATTEMPTS = 8


def _enqueue_or_mark(rec: InboundEventRecord) -> dict[str, Any]:
    try:
        from services.job_queue import job_queue

        if (
            getattr(job_queue, "backend", None) == "redis"
            and getattr(job_queue, "production_ready", False)
            and redis_required()
        ):
            job = job_queue.enqueue(
                queue="high_priority",
                job_type="meta_inbound_process",
                tenant_id=rec.tenant_id or "unknown",
                payload={
                    "event_id": rec.event_id,
                    "kind": rec.kind,
                    "_conversation_key": rec.conversation_key,
                    "_provider": "openai",
                    "_priority": "customer_conversation",
                },
                idempotency_key=f"meta_inbound:{rec.event_id}:r{rec.attempts}",
            )
            mark_inbound_state(rec.event_id, state="queued", queue_job_id=str(job.id), bump_attempts=True)
            return {"event_id": rec.event_id, "action": "requeued", "job_id": job.id}
    except Exception as exc:
        _runtime_logger.warning(
            "[inbound-reconcile] enqueue_failed event_id=%s type=%s",
            rec.event_id,
            type(exc).__name__,
        )
    # Queue unavailable: leave accepted/failed for next tick / local operator retry.
    mark_inbound_state(rec.event_id, state="accepted", bump_attempts=True)
    return {"event_id": rec.event_id, "action": "marked_accepted_for_retry"}


def reconcile_stuck_inbound_events(*, older_than_seconds: float = 45.0) -> dict[str, Any]:
    """Re-enqueue unfinished durable events. Never drops accepted records."""
    stuck = list_active_inbound_events(older_than_seconds=older_than_seconds)
    actions: list[dict[str, Any]] = []
    for rec in stuck:
        if rec.attempts >= _MAX_ATTEMPTS:
            mark_inbound_state(
                rec.event_id,
                state="dead_letter",
                last_error=rec.last_error or "max_reconcile_attempts",
            )
            actions.append({"event_id": rec.event_id, "action": "dead_letter"})
            continue
        actions.append(_enqueue_or_mark(rec))
    stats = accountability_stats()
    return {
        "reconciled_at": time.time(),
        "examined": len(stuck),
        "actions": actions,
        "accountability": stats,
        "unexplained_missing_events": int(stats.get("unexplained_missing_events") or 0),
    }


def seed_accepted_for_tests(record: InboundEventRecord) -> InboundEventRecord:
    """Test helper — write a durable accepted event without going through webhook."""
    return put_inbound_event(record)
