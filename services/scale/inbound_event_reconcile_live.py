"""Watchdog: do not enqueue a second job while ingress idempotency still owns one."""

from __future__ import annotations

from typing import Any

from services.scale.inbound_event_store import InboundEventRecord, mark_inbound_state


def ingress_idempotency_key(event_id: str) -> str:
    return f"meta_inbound:{event_id}"


def _physical_queue_for_record(rec: InboundEventRecord) -> str:
    from services.omnichannel.queues import logical_for_channel, physical_queue_for

    surface = "comment" if rec.kind == "meta_comment" else "dm"
    logical = logical_for_channel(channel="meta", surface=surface)
    return physical_queue_for(logical)


class IngressJobLookupError(Exception):
    """Redis lookup failed; caller must not enqueue :r{attempts} this tick."""


def lookup_ingress_job(rec: InboundEventRecord) -> Any:
    from services.job_queue import job_queue
    from services.queues.config import redis_required

    if getattr(job_queue, "backend", None) != "redis" or not getattr(job_queue, "production_ready", False):
        return None
    if not redis_required():
        return None
    getter = getattr(job_queue, "get_by_idempotency", None)
    if getter is None:
        raise IngressJobLookupError("get_by_idempotency missing")
    try:
        return getter(
            _physical_queue_for_record(rec),
            rec.tenant_id or "unknown",
            ingress_idempotency_key(rec.event_id),
        )
    except IngressJobLookupError:
        raise
    except Exception as exc:
        raise IngressJobLookupError(type(exc).__name__) from exc


def action_if_ingress_job_already_owns(rec: InboundEventRecord) -> dict[str, Any] | None:
    job = lookup_ingress_job(rec)
    if job is None:
        return None
    status = str(getattr(job, "status", "") or "")
    job_id = str(getattr(job, "id", "") or "")
    if status in {"queued", "processing"}:
        return {
            "event_id": rec.event_id,
            "action": "ingress_job_live",
            "job_id": job_id,
            "status": status,
        }
    if status == "completed":
        mark_inbound_state(
            rec.event_id,
            state="completed",
            last_error="reconcile_catchup_redis_completed",
        )
        return {
            "event_id": rec.event_id,
            "action": "ledger_catchup_completed",
            "job_id": job_id,
        }
    return None
