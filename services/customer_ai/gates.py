"""Cheap eligibility gates before any provider call."""

from __future__ import annotations

from dataclasses import dataclass

from services.cm.version_store import PublishedVersionError, read_published_pointer
from services.customer_ai.contracts.enums import StopReason
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.control import live_handoff_active
from services.customer_ai.policies.restricted import find_published_restricted


@dataclass(frozen=True)
class GateDecision:
    allow: bool
    reason: StopReason
    detail: str = ""
    reply_text: str = ""


def _inbound_text(turn: CustomerTurn, message: str = "") -> str:
    if (message or "").strip():
        return message
    for item in turn.history.messages:
        if item.is_current_inbound:
            return item.text
    return ""


def evaluate_gates(turn: CustomerTurn, *, apply_credits: bool = True, message: str = "") -> GateDecision:
    tenant_id = (turn.tenant_id or "").strip()
    if not tenant_id:
        return GateDecision(False, "unpublished", "missing_tenant")
    if turn.media.safety_blocked:
        return GateDecision(False, "policy_suppressed", "inbound_media_blocked")
    if turn.state.handoff_active or live_handoff_active(
        user_id=turn.customer_id,
        conversation_id=turn.conversation_id,
    ):
        return GateDecision(False, "human_control", "handoff_active")
    if apply_credits:
        from services.membership.generative_gate import generative_block_reason

        reason = generative_block_reason(tenant_id)
        if reason:
            return GateDecision(False, reason)  # type: ignore[arg-type]
    try:
        pointer = read_published_pointer(tenant_id)
    except PublishedVersionError:
        return GateDecision(False, "unpublished", "published_version_error")
    if pointer is None:
        return GateDecision(False, "unpublished", "no_published_pointer")
    inbound = _inbound_text(turn, message)
    if inbound.strip():
        topic = find_published_restricted(tenant_id, inbound)
        if topic is not None:
            from services.customer_ai.policies.restricted import refuse_text

            return GateDecision(False, "restricted", topic.id, reply_text=refuse_text(topic, inbound))
    return GateDecision(True, "ok")
