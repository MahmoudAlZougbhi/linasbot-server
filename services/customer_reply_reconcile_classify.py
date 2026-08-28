"""Classify stuck customer reply events for safe reconciliation (A/B/C/D)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from services.ai_reply_lifecycle import (
    TERMINAL_BLOCKED,
    TERMINAL_DELIVERED,
    AiReplyTurnRecord,
    find_turn_by_external_inbound,
    find_turn_for_inbound_event,
    list_all_turns,
    turn_provider_accepted,
)
from services.durable_event_claim import is_stale_file_claim
from services.scale.inbound_event_store import (
    ACTIVE_STATES,
    InboundEventRecord,
    list_active_inbound_events,
)

_logger = logging.getLogger(__name__)

ReconcileClass = Literal["A", "B", "C", "D"]
ReconcileAction = Literal[
    "none",
    "requeue_ai",
    "retry_delivery",
    "mark_ambiguous",
    "complete_inbound",
]

_DELIVERED_OUTBOUND = frozenset({"sent", "delivered", "simulated"})
_AI_INCOMPLETE_STATES = frozenset(
    {
        "RECEIVED_NO_CHARGE",
        "AI_PENDING",
        "AI_PROCESSING",
        "AI_RETRY_REQUIRED",
        "NO_FINAL_CHARGE",
    }
)
_DELIVERY_PENDING_STATES = frozenset(
    {
        "REPLY_PERSISTED",
        "CREDIT_CAPTURED_ONCE",
        "OUTBOUND_PENDING",
        "OUTBOUND_RETRY",
        "DELIVERY_RETRY_WITHOUT_REGENERATION",
        "REPLY_SAVED",
    }
)


@dataclass
class ReconcileCandidate:
    inbound_event_id: str
    classification: ReconcileClass
    action: ReconcileAction
    reason: str
    logical_reply_id: str | None = None
    claim_key_basis: str | None = None
    stale_claim: bool = False
    inbound_state: str | None = None
    turn_state: str | None = None
    has_saved_reply: bool = False
    credit_captured: bool = False
    delivered: bool = False
    reconcile_attempts: int = 0
    expected_outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _external_inbound_id(event: InboundEventRecord) -> str:
    payload = event.payload or {}
    for key in ("message_id", "mid", "source_message_id"):
        val = str(payload.get(key) or "").strip()
        if val:
            return val
    return ""


def _channel_from_event(event: InboundEventRecord) -> str:
    payload = event.payload or {}
    for key in ("channel", "platform"):
        val = str(payload.get(key) or "").strip().lower()
        if val:
            return val
    conv = event.conversation_key or ""
    if ":instagram:" in conv:
        return "instagram"
    if ":facebook:" in conv:
        return "facebook"
    return "whatsapp"


def _resolve_turn(event: InboundEventRecord) -> AiReplyTurnRecord | None:
    turn = find_turn_for_inbound_event(event.event_id)
    if turn is not None:
        return turn
    external_id = _external_inbound_id(event)
    if not external_id:
        return None
    return find_turn_by_external_inbound(
        tenant_id=event.tenant_id,
        channel=_channel_from_event(event),
        external_inbound_id=external_id,
    )


def _has_delivery_proof(event: InboundEventRecord, turn: AiReplyTurnRecord | None) -> bool:
    if turn is not None and turn.state in TERMINAL_DELIVERED:
        return True
    if turn is not None and turn.delivery_evidence.get("success"):
        return True
    outbound = str(event.outbound_status or "").strip().lower()
    return outbound in _DELIVERED_OUTBOUND


def _is_ambiguous(event: InboundEventRecord, turn: AiReplyTurnRecord | None) -> str | None:
    if turn is None:
        return None
    if turn.credit_captured and not turn.generated_reply:
        return "credit_captured_without_saved_reply"
    if turn.generated_reply and turn.state == "PERMANENT_DELIVERY_BLOCK":
        return f"blocked_turn_state:{turn.state}"
    if turn.generated_reply and turn.state == "NEEDS_OWNER_ACTION" and turn_provider_accepted(turn):
        return "blocked_turn_state:NEEDS_OWNER_ACTION"
    if event.state == "completed" and turn.state not in TERMINAL_DELIVERED | TERMINAL_BLOCKED:
        if not _has_delivery_proof(event, turn):
            if turn.generated_reply:
                return None
            return "inbound_completed_without_delivery_proof"
    if turn.retry_count >= 8 and turn.state not in TERMINAL_DELIVERED | TERMINAL_BLOCKED:
        return "max_delivery_retries_exceeded"
    return None


def classify_event_turn(
    event: InboundEventRecord,
    turn: AiReplyTurnRecord | None,
    *,
    claim_ttl_seconds: float = 120.0,
) -> ReconcileCandidate:
    """Map one inbound event + optional turn to A/B/C/D with a safe action."""
    claim_basis = turn.claim_key_basis if turn else None
    stale_claim = bool(
        claim_basis and is_stale_file_claim("ai_turn_claims", claim_basis, ttl_seconds=claim_ttl_seconds)
    )

    base = ReconcileCandidate(
        inbound_event_id=event.event_id,
        classification="D",
        action="mark_ambiguous",
        reason="unclassified",
        logical_reply_id=turn.logical_reply_id if turn else None,
        claim_key_basis=claim_basis,
        stale_claim=stale_claim,
        inbound_state=event.state,
        turn_state=turn.state if turn else None,
        has_saved_reply=bool(turn and turn.generated_reply),
        credit_captured=bool(turn and turn.credit_captured),
        delivered=_has_delivery_proof(event, turn),
        reconcile_attempts=int(event.attempts or 0),
    )

    if str(event.last_error or "").startswith("reconcile_ambiguous:"):
        from services.scale.inbound_undelivered import is_completed_undelivered

        if not is_completed_undelivered(event):
            base.action = "none"
            base.reason = "already_marked_ambiguous"
            base.expected_outcome = "no_customer_reply_or_credit_change"
            return base

    ambiguous = _is_ambiguous(event, turn)
    if ambiguous:
        base.classification = "D"
        base.action = "mark_ambiguous"
        base.reason = ambiguous
        base.expected_outcome = "manual_investigation_before_retry"
        return base

    if _has_delivery_proof(event, turn):
        base.classification = "C"
        base.action = "complete_inbound" if event.state in ACTIVE_STATES else "none"
        base.reason = "delivered_successfully"
        base.expected_outcome = "no_customer_reply_or_credit_change"
        return base

    never_sent_owner = bool(
        turn and turn.generated_reply and turn.state == "NEEDS_OWNER_ACTION" and not turn_provider_accepted(turn)
    )
    if (
        turn
        and turn.generated_reply
        and (turn.state in _DELIVERY_PENDING_STATES | {"AI_GENERATED"} or never_sent_owner)
    ):
        base.classification = "B"
        base.action = "retry_delivery"
        base.reason = "never_sent_owner_action_retry" if never_sent_owner else "reply_persisted_delivery_pending"
        base.expected_outcome = "delivery_retry_without_ai_or_credit"
        return base

    if turn is None or not turn.generated_reply or turn.state in _AI_INCOMPLETE_STATES:
        base.classification = "A"
        base.action = "requeue_ai"
        reason = "ai_never_generated_reply"
        if stale_claim:
            reason = "stale_claim_release_and_requeue_ai"
        elif turn and turn.state == "AI_PROCESSING":
            reason = "stuck_ai_processing"
        base.reason = reason
        base.expected_outcome = "single_ai_generation_with_normal_credit"
        return base

    base.classification = "D"
    base.action = "mark_ambiguous"
    base.reason = f"unhandled_turn_state:{turn.state if turn else 'missing'}"
    base.expected_outcome = "manual_investigation_before_retry"
    return base


def scan_reconcile_candidates(
    *,
    older_than_seconds: float = 60.0,
    claim_ttl_seconds: float = 120.0,
) -> list[ReconcileCandidate]:
    """Collect stuck inbound events and classify each without mutating state."""
    from services.scale.inbound_undelivered import list_completed_undelivered_meta_dms

    try:
        events = list_active_inbound_events(older_than_seconds=older_than_seconds)
    except Exception as exc:
        _logger.warning("[reconcile-scan] active_list_failed type=%s", type(exc).__name__)
        events = []
    candidates: list[ReconcileCandidate] = []
    seen_event_ids: set[str] = set()

    for event in events:
        turn = _resolve_turn(event)
        candidate = classify_event_turn(event, turn, claim_ttl_seconds=claim_ttl_seconds)
        candidates.append(candidate)
        seen_event_ids.add(event.event_id)

    try:
        undelivered = list_completed_undelivered_meta_dms(older_than_seconds=older_than_seconds)
    except Exception as exc:
        _logger.warning("[reconcile-scan] undelivered_list_failed type=%s", type(exc).__name__)
        undelivered = []
    for event in undelivered:
        if event.event_id in seen_event_ids:
            continue
        turn = _resolve_turn(event)
        candidates.append(classify_event_turn(event, turn, claim_ttl_seconds=claim_ttl_seconds))
        seen_event_ids.add(event.event_id)

    # Orphan turns: saved reply but no active inbound event linkage.
    try:
        turns = list_all_turns()
    except Exception as exc:
        _logger.warning("[reconcile-scan] turn_list_failed type=%s", type(exc).__name__)
        turns = []
    for turn in turns:
        if turn.state in TERMINAL_DELIVERED:
            continue
        if turn.state == "PERMANENT_DELIVERY_BLOCK":
            continue
        if turn.state == "NEEDS_OWNER_ACTION" and turn_provider_accepted(turn):
            continue
        if turn.inbound_event_id and turn.inbound_event_id in seen_event_ids:
            continue
        if not turn.generated_reply:
            continue
        pseudo = InboundEventRecord(
            event_id=turn.inbound_event_id or f"orphan:{turn.logical_reply_id}",
            kind="meta_dm",
            tenant_id=turn.tenant_id,
            claim_namespace="orphan_turn",
            claim_key=turn.external_inbound_id,
            state="failed",
            created_at=turn.created_at,
            updated_at=turn.updated_at,
            payload={"message_id": turn.external_inbound_id, "channel": turn.channel},
            attempts=turn.retry_count,
        )
        candidate = classify_event_turn(pseudo, turn, claim_ttl_seconds=claim_ttl_seconds)
        if candidate.classification != "C":
            candidates.append(candidate)

    return candidates


def summarize_candidates(candidates: list[ReconcileCandidate]) -> dict[str, Any]:
    """Aggregate candidate counts for dry-run reports and metrics."""
    by_class: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    by_action: dict[str, int] = {}
    stale_claims = 0
    charged_without_delivery = 0
    for item in candidates:
        by_class[item.classification] = by_class.get(item.classification, 0) + 1
        by_action[item.action] = by_action.get(item.action, 0) + 1
        if item.stale_claim:
            stale_claims += 1
        if item.credit_captured and not item.delivered:
            charged_without_delivery += 1
    return {
        "examined": len(candidates),
        "by_classification": by_class,
        "by_action": by_action,
        "stale_claims_count": stale_claims,
        "charged_without_delivery_count": charged_without_delivery,
        "stuck_events_count": sum(1 for item in candidates if item.action not in {"none", "complete_inbound"}),
        "generated_at": time.time(),
    }
