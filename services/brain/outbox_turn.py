"""Persist a finished Brain turn into the durable outbox."""

from __future__ import annotations

from services.brain.contracts.reply import TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.outbox import OutboxItem, OutboxPersistError, enqueue_envelope


def persist_turn_result(turn: CustomerTurn, result: TurnResult) -> OutboxItem | None:
    if not any((item.text or "").strip() for item in result.envelope.messages):
        return None
    extra = dict(result.extra or {})
    op = str(extra.get("operation_id") or "").strip()
    if not op:
        return None
    inbound = ""
    if turn.history.messages:
        current = next((m for m in reversed(turn.history.messages) if m.is_current_inbound), None)
        inbound = (current.text if current else turn.history.messages[-1].text) or ""
    if not inbound and turn.followup_goal:
        inbound = f"Follow-up: {turn.followup_goal}"
    try:
        return enqueue_envelope(
            tenant_id=turn.tenant_id,
            operation_id=op,
            envelope=result.envelope,
            reservation_id=op,
            billing_policy=str(extra.get("billing_policy") or "legacy_credits"),
            extra={
                "channel": turn.channel,
                "conversation_id": turn.conversation_id,
                "surface": turn.surface,
                "invocation_kind": turn.invocation_kind,
                "inbound_preview": (inbound or "")[:280],
                "phase": extra.get("phase"),
                "stop_reason": result.stop_reason,
                "message_units": extra.get("message_units"),
                "response_class": extra.get("response_class"),
                "billing_policy": extra.get("billing_policy"),
                "used_evidence_ids": extra.get("used_evidence_ids") or result.envelope.used_evidence_ids,
                "evidence_preview": extra.get("evidence_preview") or [],
                "stage_timeline": extra.get("stage_timeline") or [],
                "plan_tasks": [
                    {"id": task.get("id"), "type": task.get("type")}
                    for task in ((extra.get("plan") or {}).get("tasks") or [])
                    if isinstance(task, dict)
                ],
            },
        )
    except OutboxPersistError as exc:
        from services.brain.silence import log_customer_generation_failure

        log_customer_generation_failure(
            stage="outbox_persist",
            extra={
                "exception_class": type(exc).__name__,
                "blocker": str(exc)[:200],
                "tenant_id": turn.tenant_id,
            },
        )
        raise
