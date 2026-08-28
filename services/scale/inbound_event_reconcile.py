"""Reconcile stuck durable inbound events (watchdog / restart recovery)."""

from __future__ import annotations

import logging
import os
import time
from functools import partial
from typing import Any

from services.queues.config import redis_required
from services.scale.inbound_event_store import (
    ACTIVE_STATES,
    InboundEventRecord,
    InboundEventStoreUnavailableError,
    accountability_stats,
    get_inbound_event,
    list_active_inbound_events,
    mark_inbound_state,
    put_inbound_event,
)

_runtime_logger = logging.getLogger("uvicorn.error")
_MAX_ATTEMPTS = 8


def _claim_contract(rec: InboundEventRecord) -> tuple[str, str]:
    from services.meta_cross_flow_dedup import GLOBAL_COMMENT_CLAIM_NAMESPACE, GLOBAL_DM_CLAIM_NAMESPACE

    if rec.kind == "meta_dm":
        return GLOBAL_DM_CLAIM_NAMESPACE, "meta_social_dm_global_claims"
    return GLOBAL_COMMENT_CLAIM_NAMESPACE, "meta_social_comment_global_claims"


def _enqueue_or_mark(rec: InboundEventRecord, claim_handle: Any) -> dict[str, Any]:
    queue_available = False
    try:
        from services.job_queue import job_queue

        queue_available = bool(
            getattr(job_queue, "backend", None) == "redis"
            and getattr(job_queue, "production_ready", False)
            and redis_required()
        )
        if queue_available:
            from services.omnichannel.queues import logical_for_channel, physical_queue_for

            surface = "comment" if rec.kind == "meta_comment" else "dm"
            logical = logical_for_channel(channel="meta", surface=surface)
            job = job_queue.enqueue(
                queue=physical_queue_for(logical),  # type: ignore[arg-type]
                job_type="meta_inbound_process",
                tenant_id=rec.tenant_id or "unknown",
                payload={
                    "event_id": rec.event_id,
                    "kind": rec.kind,
                    "_conversation_key": rec.conversation_key,
                    "_provider": "openai",
                    "_priority": "background" if surface == "comment" else "customer_conversation",
                    "_logical_queue": logical,
                    "_claim_token": claim_handle.owner_token,
                    "_claim_generation": claim_handle.generation,
                    "_linas_soak_simulation": bool((rec.payload or {}).get("_linas_soak_simulation")),
                },
                idempotency_key=f"meta_inbound:{rec.event_id}:r{rec.attempts}",
            )
            try:
                mark_inbound_state(rec.event_id, state="queued", queue_job_id=str(job.id), bump_attempts=True)
            except Exception as exc:
                _runtime_logger.warning(
                    "[inbound-reconcile] enqueued_ledger_update_failed event_id=%s type=%s",
                    rec.event_id,
                    type(exc).__name__,
                )
                return {"event_id": rec.event_id, "action": "requeued_ledger_update_failed", "job_id": job.id}
            return {"event_id": rec.event_id, "action": "requeued", "job_id": job.id}
    except Exception as exc:
        _runtime_logger.warning(
            "[inbound-reconcile] enqueue_failed event_id=%s type=%s",
            rec.event_id,
            type(exc).__name__,
        )
        if queue_available:
            # Redis may have accepted the deterministic job before the ACK was
            # lost. Retain the claim; releasing it would let two consumers run.
            try:
                mark_inbound_state(rec.event_id, state="queued", last_error="enqueue_ack_unknown")
            except Exception:
                pass
            return {"event_id": rec.event_id, "action": "enqueue_ack_unknown"}
    # Queue was proven unavailable before an enqueue attempt. Release safely so
    # a later tick can retry without waiting for lease expiry.
    mark_inbound_state(rec.event_id, state="accepted", bump_attempts=True)
    from services.durable_event_claim import release_event_claim, run_claim_coroutine_blocking

    namespace, collection = _claim_contract(rec)
    run_claim_coroutine_blocking(
        lambda: release_event_claim(
            namespace,
            rec.claim_key,
            firestore_collection=collection,
            claim_handle=claim_handle,
        )
    )
    return {"event_id": rec.event_id, "action": "marked_accepted_for_retry"}


def _disarmed_soak_action(rec: InboundEventRecord) -> dict[str, Any] | None:
    if not bool((rec.payload or {}).get("_linas_soak_simulation")):
        return None
    from services.scale.soak_arm import is_armed

    if is_armed():
        return None
    mark_inbound_state(
        rec.event_id,
        state="completed",
        outbound_status="simulated",
        last_error="soak_disarmed",
    )
    return {"event_id": rec.event_id, "action": "soak_aborted_disarmed"}


def _requeue_one_stuck(rec: InboundEventRecord) -> dict[str, Any]:
    soak = _disarmed_soak_action(rec)
    if soak is not None:
        return soak
    from services.durable_event_claim import (
        complete_event_claim,
        meta_claim_binding_digest,
        run_claim_coroutine_blocking,
        try_claim_event_handle,
    )

    namespace, collection = _claim_contract(rec)
    claim_handle = run_claim_coroutine_blocking(
        partial(
            try_claim_event_handle,
            namespace,
            rec.claim_key,
            ttl_seconds=300.0,
            firestore_collection=collection,
            firestore_claim_metadata={
                "binding_id_sha256": meta_claim_binding_digest(
                    str(rec.binding_snapshot.get("binding_id") or rec.settings_snapshot.get("binding_id") or "")
                ),
                "inbound_event_id": rec.event_id,
            },
            meta_binding_id=str(
                rec.binding_snapshot.get("binding_id") or rec.settings_snapshot.get("binding_id") or ""
            ),
        )
    )
    if claim_handle is None:
        return {"event_id": rec.event_id, "action": "live_claim_skipped"}
    if rec.attempts >= _MAX_ATTEMPTS:
        mark_inbound_state(
            rec.event_id,
            state="dead_letter",
            last_error=rec.last_error or "max_reconcile_attempts",
        )
        run_claim_coroutine_blocking(
            partial(
                complete_event_claim,
                namespace,
                rec.claim_key,
                firestore_collection=collection,
                claim_handle=claim_handle,
            )
        )
        return {"event_id": rec.event_id, "action": "dead_letter"}
    return _enqueue_or_mark(rec, claim_handle)


def requeue_inbound_event_ids(event_ids: list[str]) -> list[dict[str, Any]]:
    """Enqueue specific reopened events when the active Firestore scan cannot run."""
    actions: list[dict[str, Any]] = []
    for event_id in event_ids:
        if not event_id or event_id.startswith("orphan:"):
            continue
        try:
            rec = get_inbound_event(event_id)
        except Exception as exc:
            _runtime_logger.warning(
                "[inbound-reconcile] targeted_get_failed event_id=%s type=%s",
                event_id,
                type(exc).__name__,
            )
            continue
        if rec is None or rec.state not in ACTIVE_STATES:
            continue
        try:
            actions.append(_requeue_one_stuck(rec))
        except Exception as exc:
            _runtime_logger.warning(
                "[inbound-reconcile] targeted_requeue_failed event_id=%s type=%s",
                event_id,
                type(exc).__name__,
            )
            actions.append({"event_id": event_id, "action": "requeue_failed", "reason": type(exc).__name__})
    return actions


def reconcile_stuck_inbound_events(*, older_than_seconds: float = 45.0) -> dict[str, Any]:
    """Re-enqueue unfinished durable events. Never drops accepted records."""
    stuck = list_active_inbound_events(older_than_seconds=older_than_seconds)
    raw_limit = (os.getenv("LINAS_INBOUND_RECONCILE_BATCH") or "32").strip()
    try:
        limit = max(1, min(200, int(raw_limit)))
    except ValueError:
        limit = 32
    stuck = stuck[:limit]
    actions: list[dict[str, Any]] = []
    for rec in stuck:
        try:
            actions.append(_requeue_one_stuck(rec))
        except Exception as exc:
            _runtime_logger.warning(
                "[inbound-reconcile] requeue_one_failed event_id=%s type=%s",
                rec.event_id,
                type(exc).__name__,
            )
            actions.append(
                {
                    "event_id": rec.event_id,
                    "action": "requeue_failed",
                    "reason": type(exc).__name__,
                }
            )
    try:
        stats = accountability_stats()
    except InboundEventStoreUnavailableError:
        _runtime_logger.warning("[inbound-reconcile] accountability_audit_failed")
        stats = {
            "accepted_total": len(stuck),
            "terminal_accounted": 0,
            "active_non_terminal": len(stuck),
            "unexplained_missing_events": 0,
        }
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
