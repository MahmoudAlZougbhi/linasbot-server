"""Isolated Customer Brain lab. Capture-only; no live channel send."""

from __future__ import annotations

import os
from typing import Any

from services.customer_ai.billing import operation_id_for_turn
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
from services.customer_ai.outbox_test import save_envelope_for_test
from services.membership.message_policy import message_units_for


def lab_enabled() -> bool:
    return (os.getenv("LINAS_CUSTOMER_AI_LAB") or "").strip().lower() in {"1", "true", "yes", "on"}


async def run_lab_turn(
    *,
    tenant_id: str,
    message: str,
    conversation_id: str = "lab:conv",
    user_id: str = "lab:user",
    channel: str = "web_chat",
    message_id: str = "",
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not lab_enabled():
        return {"ok": False, "reason": "lab_disabled"}
    from services.customer_ai.flags import customer_brain_enabled
    from services.customer_ai.runtime import run_customer_ai_dm

    if not customer_brain_enabled():
        return {"ok": False, "reason": "brain_disabled"}
    inbound_id = message_id or f"lab:{conversation_id}:{len(history or [])}"
    channel_name = channel or "web_chat"
    meta: dict[str, Any] = {}
    try:
        outcome = await run_customer_ai_dm(
            tenant_id=tenant_id,
            message=message,
            channel=channel_name,
            conversation_id=conversation_id,
            user_id=user_id,
            injected_history=history,
            message_id=inbound_id,
            apply_customer_usage_limits=True,
        )
        raw = getattr(outcome, "metadata", None) or {}
        meta = raw if isinstance(raw, dict) else {}
        response_class = str(meta.get("response_class") or "operational_notice")
        try:
            units = message_units_for(response_class)  # type: ignore[arg-type]
        except Exception:
            units = 0
        reply = str(getattr(outcome, "reply", None) or "")
        save_envelope_for_test(
            FinalReplyEnvelope(
                decision="reply" if reply else "no_reply",
                messages=[OutboundMessage(destination="dm", text=reply)] if reply else [],
            ),
            tenant_id=tenant_id,
            reason=getattr(outcome, "reason", ""),
            metadata=meta,
        )
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "channel": channel_name,
            "message_id": inbound_id,
            "reply": getattr(outcome, "reply", None),
            "stop": getattr(outcome, "stop", False),
            "reason": getattr(outcome, "reason", ""),
            "response_class": response_class,
            "message_units": units,
            "operation_id": meta.get("operation_id") or "",
            "outbound_messages": meta.get("outbound_messages") or [],
            "receipts": list(meta.get("receipts") or []),
            "pending_actions": list(meta.get("pending_actions") or []),
            "retrieval_outcome": meta.get("retrieval_outcome"),
            "used_evidence_ids": list(meta.get("used_evidence_ids") or []),
            "awaiting_confirmation": bool(meta.get("awaiting_confirmation")),
            "live_send": False,
        }
    finally:
        from services.customer_ai.billing import settle_after_send

        settle_after_send(
            tenant_id=tenant_id,
            operation_id=str(meta.get("operation_id") or inbound_id),
            accepted=False,
            channel=channel_name,
            extra_ids=(inbound_id, conversation_id, message_id),
        )


def lab_operation_id(tenant_id: str, conversation_id: str, message_id: str) -> str:
    from services.customer_ai.contracts.turn import CustomerTurn

    turn = CustomerTurn(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event_ids=[message_id],
    )
    return operation_id_for_turn(turn)


def run_lab_verification_exercises(*, tenant_id: str = "lab") -> dict[str, Any]:
    """Offline lab checks: confirmation copy, index readiness, retrieval outcomes.

    Does not bill real customers (no live send; readiness/eval only).
    """
    from services.customer_ai.evals.runner import run_fixture_corpus
    from services.customer_ai.search.readiness import search_readiness
    from services.customer_ai.templates import brain_template

    readiness = search_readiness()
    confirm_en = brain_template("confirm_request", "en")
    confirm_ar = brain_template("confirm_request", "ar")
    evals = run_fixture_corpus()
    exercises = [
        {
            "id": "confirmation_copy",
            "ok": bool(confirm_en.strip()) and bool(confirm_ar.strip()) and confirm_en != confirm_ar,
            "detail": {"en": confirm_en, "ar": confirm_ar},
        },
        {
            "id": "index_readiness_typed",
            "ok": isinstance(getattr(readiness, "ready", None), bool)
            and bool(getattr(readiness, "reason", "") or readiness.ready),
            "detail": {
                "ready": bool(getattr(readiness, "ready", False)),
                "reason": str(getattr(readiness, "reason", "") or ""),
            },
        },
        {
            "id": "retrieval_eval_suite",
            "ok": bool(evals.get("ok")),
            "detail": {
                "case_count": evals.get("case_count"),
                "golden_ok": (evals.get("golden_pack_linas") or {}).get("ok"),
                "metrics": evals.get("metrics"),
            },
        },
        {
            "id": "no_live_billing",
            "ok": evals.get("live_spend") is False,
            "detail": {"tenant_id": tenant_id, "live_send": False},
        },
    ]
    return {
        "ok": all(bool(item.get("ok")) for item in exercises),
        "tenant_id": tenant_id,
        "live_send": False,
        "exercises": exercises,
        "evals": evals,
    }
