"""Idempotent Smart Follow-Up delivery for website chat visitors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT
from services.smart_followup.idempotency import canonical_sfu_credit_request_id, canonical_sfu_key
from services.web_chat.operation import (
    OperationRuntime,
    abandon_operation_lease,
    advance_operation,
    begin_operation,
    build_followup_payload,
    operation_session,
    reconcile_billing_pending,
    refresh_operation_lease,
    refresh_operation_runtime,
    try_advance_operation,
    web_chat_operation_repository,
)
from services.web_chat.operation_fsm import OperationFsmError, OperationState, stable_operation_key
from services.web_chat.persistence import PersistFailure, PersistOutcome, persist_web_chat_message
from services.web_chat.session_authority import verified_session_snapshot
from services.web_chat.session_binding import FollowUpSessionBoundaryError, resolve_durable_visitor_binding
from services.web_chat.store import WebChatStoreBackend, web_chat_store


@dataclass(frozen=True)
class WebFollowUpDeliveryResult:
    status: Literal["delivered", "already_delivered"]
    idempotency_key: str
    billing_captured: bool = False
    billing_pending: bool = False


def _duplicate_delivery_result(key: str) -> WebFollowUpDeliveryResult:
    return WebFollowUpDeliveryResult(status="already_delivered", idempotency_key=key)


def _maybe_followup_failpoint(name: str) -> None:
    if os.environ.get("WEB_CHAT_FOLLOWUP_FAILPOINT") == name:
        raise RuntimeError(f"failpoint:{name}")


def _outbox_visible_needs_convergence(
    *,
    active_store: WebChatStoreBackend,
    visitor_id: str,
    key: str,
    runtime: OperationRuntime,
) -> bool:
    if not active_store.has_assistant_delivery(visitor_id, key):
        return False
    record = runtime.record
    return record is None or record.state != OperationState.COMPLETE


async def _converge_from_durable_outbox(
    *,
    runtime: OperationRuntime,
    tid: str,
    key: str,
    turn_result: dict,
    bound_reservation_id: str,
) -> WebFollowUpDeliveryResult:
    """Resume billing from a durable outbox row under the operation fence."""
    refresh_operation_runtime(runtime)
    record = runtime.record
    if record is None:
        raise OperationFsmError("operation_missing", "Operation not found.")
    if record.state == OperationState.COMPLETE:
        return _duplicate_delivery_result(key)
    if record.state in {OperationState.CLAIMED, OperationState.RESERVED}:
        if record.state == OperationState.CLAIMED:
            advance_operation(runtime, OperationState.RESERVED, reservation_id=bound_reservation_id)
        advance_operation(runtime, OperationState.REPLY_READY, result=turn_result)
    refresh_operation_runtime(runtime)
    record = runtime.record
    if record and record.state == OperationState.REPLY_READY:
        advance_operation(runtime, OperationState.DURABLE_VISIBLE, result=turn_result)
    captured, billing_pending = _finalize_followup_billing(
        runtime,
        tenant_id=tid,
        reservation_id=bound_reservation_id,
        idempotency_key=key,
    )
    return WebFollowUpDeliveryResult(
        status="delivered",
        idempotency_key=key,
        billing_captured=captured,
        billing_pending=billing_pending,
    )


def _resolve_bound_reservation(
    *,
    runtime: OperationRuntime,
    reservation_id: str | None,
) -> str:
    refresh_operation_runtime(runtime)
    explicit = str(reservation_id or "").strip()
    record = runtime.record
    bound = str(record.reservation_id or "").strip() if record else ""
    if explicit and bound and explicit != bound:
        raise OperationFsmError(
            "reservation_mismatch",
            "Follow-up delivery reservation does not match the bound operation.",
        )
    resolved = explicit or bound
    if not resolved:
        raise OperationFsmError(
            "reservation_required",
            "Follow-up delivery requires a bound credit reservation.",
        )
    return resolved


def _preflight_reservation_or_resume(
    *,
    tenant_id: str,
    operation_key: str,
    reservation_id: str | None,
) -> None:
    """Fail closed on brand-new deliveries with no bound reservation."""
    explicit = str(reservation_id or "").strip()
    if explicit:
        return
    with operation_session() as db:
        row = web_chat_operation_repository.get(db, tenant_id=tenant_id, operation_key=operation_key)
    if row is None:
        raise OperationFsmError(
            "reservation_required",
            "Follow-up delivery requires a bound credit reservation.",
        )
    state = OperationState(str(row.state))
    if state == OperationState.CLAIMED and not str(row.reservation_id or "").strip():
        raise OperationFsmError(
            "reservation_required",
            "Follow-up delivery requires a bound credit reservation.",
        )


def _finalize_followup_billing(
    runtime: OperationRuntime,
    *,
    tenant_id: str,
    reservation_id: str,
    idempotency_key: str,
) -> tuple[bool, bool]:
    """Capture after durable visibility; returns (captured, billing_pending)."""
    from services.credit_ledger_service import credit_ledger_service
    from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle

    refresh_operation_runtime(runtime)
    record = runtime.record
    if record is None:
        return False, False
    if record.state == OperationState.COMPLETE:
        return True, False
    if record.state == OperationState.CAPTURED:
        try_advance_operation(
            runtime,
            OperationState.CAPTURED,
            OperationState.COMPLETE,
            result=record.result,
        )
        refresh_operation_runtime(runtime)
        return bool(runtime.record and runtime.record.state == OperationState.COMPLETE), False
    if record.state == OperationState.BILLING_PENDING:
        return False, True
    if record.state != OperationState.DURABLE_VISIBLE:
        return False, False
    if not record.reservation_id:
        advance_operation(runtime, OperationState.BILLING_PENDING, result=record.result)
        abandon_operation_lease(runtime)
        return False, True

    turn_payload = record.result
    terminal = credit_ledger_service.reservation_terminal(tenant_id, reservation_id)
    if terminal == "capture":
        _, won_capture = try_advance_operation(
            runtime,
            OperationState.DURABLE_VISIBLE,
            OperationState.CAPTURED,
            result=turn_payload,
        )
        if won_capture or (runtime.record and runtime.record.state == OperationState.CAPTURED):
            try_advance_operation(
                runtime,
                OperationState.CAPTURED,
                OperationState.COMPLETE,
                result=turn_payload,
            )
        refresh_operation_runtime(runtime)
        return bool(runtime.record and runtime.record.state == OperationState.COMPLETE), False

    credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        request_id=canonical_sfu_credit_request_id(idempotency_key),
        operation_state=OperationState.DURABLE_VISIBLE,
    )
    credit.state = CreditFsmState.RESERVED
    try:
        credit.capture(model_provider="smart_followup")
    except Exception:
        advance_operation(runtime, OperationState.BILLING_PENDING, result=turn_payload)
        abandon_operation_lease(runtime)
        return False, True
    if credit.state != CreditFsmState.CAPTURED:
        advance_operation(runtime, OperationState.BILLING_PENDING, result=turn_payload)
        abandon_operation_lease(runtime)
        return False, True

    _, won_capture = try_advance_operation(
        runtime,
        OperationState.DURABLE_VISIBLE,
        OperationState.CAPTURED,
        result=turn_payload,
    )
    if not won_capture:
        refresh_operation_runtime(runtime)
        if runtime.record and runtime.record.state in {OperationState.CAPTURED, OperationState.COMPLETE}:
            return True, False
        return False, False
    try_advance_operation(
        runtime,
        OperationState.CAPTURED,
        OperationState.COMPLETE,
        result=turn_payload,
    )
    return True, False


async def _project_then_enqueue_followup(
    *,
    runtime: OperationRuntime,
    active_store: WebChatStoreBackend,
    tid: str,
    visitor_id: str,
    user_id: str,
    conversation_id: str,
    reply_text: str,
    key: str,
    turn_result: dict,
    bound_reservation_id: str,
) -> WebFollowUpDeliveryResult:
    """Typed Firestore readback, then durable outbox, then visible completion."""
    try:
        persist_result = await persist_web_chat_message(
            user_id=user_id,
            role="ai",
            text=reply_text,
            conversation_id=conversation_id,
            metadata={
                "channel": "web",
                "source": SOURCE_CHANNEL_WEB_CHAT,
                "idempotency_key": key,
                "source_message_id": key,
                "handled_by": "smart_followup",
                "tenant_id": tid,
            },
        )
    except PersistFailure:
        abandon_operation_lease(runtime)
        raise
    if persist_result.outcome not in {PersistOutcome.CREATED, PersistOutcome.DUPLICATE}:
        abandon_operation_lease(runtime)
        raise PersistFailure("firestore_unavailable", "Firestore projection did not commit.")

    try:
        queued = active_store.queue_assistant_message(visitor_id, reply_text, idempotency_key=key)
    except Exception:
        abandon_operation_lease(runtime)
        raise

    if not queued:
        return await _converge_from_durable_outbox(
            runtime=runtime,
            tid=tid,
            key=key,
            turn_result=turn_result,
            bound_reservation_id=bound_reservation_id,
        )

    try:
        _maybe_followup_failpoint("after_outbox_before_durable_visible")
        advance_operation(runtime, OperationState.DURABLE_VISIBLE, result=turn_result)
    except OperationFsmError as exc:
        if exc.code == "lease_fence_stale":
            return await _converge_from_durable_outbox(
                runtime=runtime,
                tid=tid,
                key=key,
                turn_result=turn_result,
                bound_reservation_id=bound_reservation_id,
            )
        abandon_operation_lease(runtime)
        raise
    except Exception:
        abandon_operation_lease(runtime)
        raise
    captured, billing_pending = _finalize_followup_billing(
        runtime,
        tenant_id=tid,
        reservation_id=bound_reservation_id,
        idempotency_key=key,
    )
    return WebFollowUpDeliveryResult(
        status="delivered",
        idempotency_key=key,
        billing_captured=captured,
        billing_pending=billing_pending,
    )


async def deliver_web_followup_message(
    *,
    tenant_id: str,
    visitor_id: str,
    user_id: str,
    conversation_id: str,
    reply_text: str,
    idempotency_key: str,
    widget_key: str,
    authority_hash: str = "",
    store: WebChatStoreBackend | None = None,
    reservation_id: str | None = None,
) -> WebFollowUpDeliveryResult:
    """Persist then enqueue one assistant follow-up keyed by ``idempotency_key``."""
    key = canonical_sfu_key(idempotency_key)
    tid = str(tenant_id or "").strip().lower()
    active_store = store or web_chat_store
    binding = resolve_durable_visitor_binding(
        store=active_store,
        visitor_id=visitor_id,
        expected_tenant_id=tid,
        expected_widget_key=widget_key,
    )
    operation_key = stable_operation_key(session_id=visitor_id, client_key=key)
    snapshot = verified_session_snapshot(
        tenant_id=binding.tenant_id,
        widget_key=binding.widget_key,
        session_id=binding.session_id,
        authority_hash=binding.authority_hash,
    )
    payload = build_followup_payload(visitor_id=visitor_id, reply_text=reply_text, idempotency_key=key)
    turn_result = {"reply_text": reply_text, "idempotency_key": key}

    _preflight_reservation_or_resume(
        tenant_id=tid,
        operation_key=operation_key,
        reservation_id=reservation_id,
    )

    try:
        runtime = begin_operation(
            tenant_id=tid,
            operation_key=operation_key,
            payload=payload,
            snapshot=snapshot,
        )
    except OperationFsmError:
        raise

    record = runtime.record
    if _outbox_visible_needs_convergence(
        active_store=active_store,
        visitor_id=visitor_id,
        key=key,
        runtime=runtime,
    ):
        bound_reservation_id = _resolve_bound_reservation(runtime=runtime, reservation_id=reservation_id)
        return await _converge_from_durable_outbox(
            runtime=runtime,
            tid=tid,
            key=key,
            turn_result=turn_result,
            bound_reservation_id=bound_reservation_id,
        )
    if record and record.state == OperationState.COMPLETE:
        return _duplicate_delivery_result(key)

    refresh_operation_lease(runtime)

    bound_reservation_id = _resolve_bound_reservation(runtime=runtime, reservation_id=reservation_id)
    refresh_operation_runtime(runtime)
    record = runtime.record

    if record is None or record.state == OperationState.CLAIMED:
        advance_operation(runtime, OperationState.RESERVED, reservation_id=bound_reservation_id)
        advance_operation(runtime, OperationState.REPLY_READY, result=turn_result)

    return await _project_then_enqueue_followup(
        runtime=runtime,
        active_store=active_store,
        tid=tid,
        visitor_id=visitor_id,
        user_id=user_id,
        conversation_id=conversation_id,
        reply_text=reply_text,
        key=key,
        turn_result=turn_result,
        bound_reservation_id=bound_reservation_id,
    )


def reconcile_followup_credit(
    *,
    tenant_id: str,
    visitor_id: str,
    idempotency_key: str,
    reservation_id: str,
) -> bool:
    from services.web_chat.credit_fsm import WebChatCreditHandle

    operation_key = stable_operation_key(session_id=visitor_id, client_key=canonical_sfu_key(idempotency_key))
    with operation_session() as db:
        row_record = web_chat_operation_repository.get(db, tenant_id=tenant_id, operation_key=operation_key)
        if row_record is None:
            return False
        bound_reservation = row_record.reservation_id or reservation_id
        if not bound_reservation:
            return False
    credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=bound_reservation,
        request_id=canonical_sfu_credit_request_id(idempotency_key),
        operation_state=row_record.state,
    )
    record = reconcile_billing_pending(tenant_id=tenant_id, operation_key=operation_key, credit=credit)
    return bool(record and record.state == OperationState.COMPLETE)


__all__ = [
    "FollowUpSessionBoundaryError",
    "WebFollowUpDeliveryResult",
    "deliver_web_followup_message",
    "reconcile_followup_credit",
]
