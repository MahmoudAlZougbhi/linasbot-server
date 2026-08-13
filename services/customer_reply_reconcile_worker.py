"""Execute safe customer reply reconciliation for stuck inbound events."""

from __future__ import annotations

import logging
import time
from typing import Any

from services.ai_reply_lifecycle import get_turn, mark_state
from services.customer_reply_reconcile_classify import (
    ReconcileCandidate,
    scan_reconcile_candidates,
    summarize_candidates,
)
from services.scale.inbound_event_reconcile import reconcile_stuck_inbound_events
from services.scale.inbound_event_store import get_inbound_event, mark_inbound_state

_logger = logging.getLogger(__name__)

_MAX_RECONCILE_ATTEMPTS = 8
_METRICS: dict[str, int] = {
    "stuck_events_count": 0,
    "stale_claims_count": 0,
    "retry_success_count": 0,
    "charged_without_delivery_count": 0,
}


def get_reconcile_metrics() -> dict[str, int]:
    return dict(_METRICS)


def reset_reconcile_metrics() -> None:
    for key in _METRICS:
        _METRICS[key] = 0


def _record_metrics(summary: dict[str, Any], *, executed: int) -> None:
    _METRICS["stuck_events_count"] = int(summary.get("stuck_events_count") or 0)
    _METRICS["stale_claims_count"] = int(summary.get("stale_claims_count") or 0)
    _METRICS["charged_without_delivery_count"] = int(summary.get("charged_without_delivery_count") or 0)
    if executed:
        _METRICS["retry_success_count"] = _METRICS.get("retry_success_count", 0) + executed


async def _release_stale_claim(claim_key_basis: str | None) -> bool:
    if not claim_key_basis:
        return False
    from services.outbound_turn_idempotency import release_ai_turn_claim

    await release_ai_turn_claim(claim_key_basis)
    return True


def _mark_ambiguous(candidate: ReconcileCandidate) -> dict[str, Any]:
    if candidate.logical_reply_id:
        mark_state(
            candidate.logical_reply_id,
            "NEEDS_OWNER_ACTION",
            last_error=f"reconcile_ambiguous:{candidate.reason}",
        )
    event = get_inbound_event(candidate.inbound_event_id)
    if event is not None and not candidate.inbound_event_id.startswith("orphan:"):
        mark_inbound_state(
            candidate.inbound_event_id,
            state="failed",
            last_error=f"reconcile_ambiguous:{candidate.reason}",
        )
    return {"event_id": candidate.inbound_event_id, "action": "mark_ambiguous", "reason": candidate.reason}


async def _execute_candidate(candidate: ReconcileCandidate) -> dict[str, Any]:
    if candidate.reconcile_attempts >= _MAX_RECONCILE_ATTEMPTS:
        return _mark_ambiguous(candidate)

    if candidate.action == "none":
        return {"event_id": candidate.inbound_event_id, "action": "none", "reason": candidate.reason}

    if candidate.action == "complete_inbound":
        if not candidate.inbound_event_id.startswith("orphan:"):
            mark_inbound_state(
                candidate.inbound_event_id,
                state="completed",
                outbound_status="delivered",
                ai_output_persisted=candidate.has_saved_reply,
            )
        return {
            "event_id": candidate.inbound_event_id,
            "action": "complete_inbound",
            "reason": candidate.reason,
        }

    if candidate.action == "mark_ambiguous":
        return _mark_ambiguous(candidate)

    if candidate.action == "retry_delivery":
        if candidate.logical_reply_id:
            mark_state(candidate.logical_reply_id, "DELIVERY_RETRY_WITHOUT_REGENERATION")
        if not candidate.inbound_event_id.startswith("orphan:"):
            mark_inbound_state(
                candidate.inbound_event_id,
                state="accepted",
                outbound_status="retry_delivery",
                ai_output_persisted=True,
                bump_attempts=True,
            )
        return {
            "event_id": candidate.inbound_event_id,
            "action": "retry_delivery",
            "logical_reply_id": candidate.logical_reply_id,
            "reason": candidate.reason,
        }

    # A — requeue AI: release stale claim, reset turn, requeue inbound.
    released = False
    if candidate.stale_claim:
        released = await _release_stale_claim(candidate.claim_key_basis)

    if candidate.logical_reply_id:
        turn = get_turn(candidate.logical_reply_id)
        if turn is not None and not turn.generated_reply:
            if turn.state == "AI_PROCESSING":
                from services.ai_reply_credit_gate import release_on_ai_failure

                release_on_ai_failure(candidate.logical_reply_id)
            else:
                mark_state(candidate.logical_reply_id, "AI_RETRY_REQUIRED", last_error="reconcile_requeue_ai")

    if not candidate.inbound_event_id.startswith("orphan:"):
        mark_inbound_state(
            candidate.inbound_event_id,
            state="accepted",
            last_error=None,
            bump_attempts=True,
        )
    return {
        "event_id": candidate.inbound_event_id,
        "action": "requeue_ai",
        "released_stale_claim": released,
        "logical_reply_id": candidate.logical_reply_id,
        "reason": candidate.reason,
    }


def _candidate_report_row(candidate: ReconcileCandidate) -> dict[str, Any]:
    return {
        "inbound_event_id": candidate.inbound_event_id,
        "classification": candidate.classification,
        "action": candidate.action,
        "reason": candidate.reason,
        "expected_outcome": candidate.expected_outcome,
        "logical_reply_id": candidate.logical_reply_id,
        "stale_claim": candidate.stale_claim,
        "inbound_state": candidate.inbound_state,
        "turn_state": candidate.turn_state,
        "has_saved_reply": candidate.has_saved_reply,
        "credit_captured": candidate.credit_captured,
        "delivered": candidate.delivered,
        "reconcile_attempts": candidate.reconcile_attempts,
    }


async def reconcile_customer_replies(
    *,
    dry_run: bool = False,
    older_than_seconds: float = 60.0,
    claim_ttl_seconds: float = 120.0,
) -> dict[str, Any]:
    """Classify stuck events and optionally execute safe recovery actions."""
    candidates = scan_reconcile_candidates(
        older_than_seconds=older_than_seconds,
        claim_ttl_seconds=claim_ttl_seconds,
    )
    summary = summarize_candidates(candidates)
    report_rows = [_candidate_report_row(c) for c in candidates]

    if dry_run:
        _record_metrics(summary, executed=0)
        return {
            "dry_run": True,
            "reconciled_at": time.time(),
            "summary": summary,
            "metrics": get_reconcile_metrics(),
            "planned_actions": report_rows,
        }

    actions: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.action in {"none", "complete_inbound"} and candidate.classification == "C":
            actions.append(await _execute_candidate(candidate))
            continue
        if candidate.classification == "D":
            actions.append(await _execute_candidate(candidate))
            continue
        if candidate.classification in {"A", "B"}:
            actions.append(await _execute_candidate(candidate))

    # Re-enqueue durable inbound jobs after local state fixes.
    queue_result = reconcile_stuck_inbound_events(older_than_seconds=0.0)
    executed = sum(1 for a in actions if a.get("action") not in {"none"})
    _record_metrics(summary, executed=executed)

    return {
        "dry_run": False,
        "reconciled_at": time.time(),
        "summary": summary,
        "metrics": get_reconcile_metrics(),
        "actions": actions,
        "inbound_requeue": {
            "examined": queue_result.get("examined"),
            "actions": queue_result.get("actions"),
        },
    }
