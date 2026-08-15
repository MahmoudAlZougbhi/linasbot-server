"""Durable visibility, capture, billing, and completion for web chat turns."""

from __future__ import annotations

from typing import Any

from services.web_chat.credit_fsm import WebChatCreditHandle
from services.web_chat.operation import (
    OperationRuntime,
    reconcile_billing_pending,
    refresh_operation_runtime,
    try_advance_operation,
)
from services.web_chat.operation_fence import fenced_failure_release
from services.web_chat.operation_fsm import OperationState
from services.web_chat.processor import (
    WebChatError,
    _persist_web_turn,
    _replay_if_operation_visible,
)
from services.web_chat.processor_turn_finalize import (
    complete_captured_turn,
    replay_complete_with_turn_repair,
)
from services.web_chat.store import WebChatStoreBackend, WebChatWidgetConfig


def _schedule_turn_followup(
    *,
    tid: str,
    user_id: str,
    visitor_id: str,
    conversation_id: str,
    widget: WebChatWidgetConfig,
) -> None:
    try:
        import time

        from services.web_chat.followup import maybe_schedule_web_followup_after_ai_reply

        maybe_schedule_web_followup_after_ai_reply(
            tenant_id=tid,
            user_id=user_id,
            visitor_session_id=visitor_id,
            conversation_id=conversation_id,
            widget_key=widget.widget_key,
            trigger_ref=f"web:{visitor_id}:{int(time.time())}",
        )
    except Exception:
        pass


def _replay_or_raise(
    *,
    runtime: OperationRuntime,
    credit: WebChatCreditHandle,
    tid: str,
    operation_key: str,
    reply_text: str,
    error_code: str,
    error_message: str,
) -> str:
    visible = _replay_if_operation_visible(
        runtime=runtime,
        credit=credit,
        tid=tid,
        operation_key=operation_key,
        reply_text=reply_text,
    )
    if visible is not None:
        return visible
    refresh_operation_runtime(runtime)
    replay = runtime.record.canonical_reply() if runtime.record else None
    if replay:
        return replay
    raise WebChatError(error_code, error_message, status_code=409)


async def _capture_then_mark_captured(
    *,
    runtime: OperationRuntime,
    credit: WebChatCreditHandle,
    turn_result: dict[str, Any],
    tid: str,
    operation_key: str,
    reply_text: str,
) -> None:
    """Capture credits before CAPTURED; CAPTURED means capture is durably proven."""
    try:
        credit.capture()
        credit.operation_state = OperationState.CAPTURED
    except Exception as exc:
        credit.mark_billing_pending()
        try_advance_operation(
            runtime,
            OperationState.DURABLE_VISIBLE,
            OperationState.BILLING_PENDING,
            result=turn_result,
            released=False,
        )
        raise WebChatError("credit_capture_failed", "Could not finalize credits.", status_code=503) from exc

    _, won_capture = try_advance_operation(
        runtime,
        OperationState.DURABLE_VISIBLE,
        OperationState.CAPTURED,
        result=turn_result,
    )
    if not won_capture:
        refresh_operation_runtime(runtime)
        if runtime.record and runtime.record.state in {
            OperationState.CAPTURED,
            OperationState.COMPLETE,
            OperationState.BILLING_PENDING,
        }:
            return
        _replay_or_raise(
            runtime=runtime,
            credit=credit,
            tid=tid,
            operation_key=operation_key,
            reply_text=reply_text,
            error_code="operation_in_progress",
            error_message="Operation capture in progress.",
        )


async def complete_web_chat_turn(
    *,
    runtime: OperationRuntime,
    credit: WebChatCreditHandle,
    tid: str,
    operation_key: str,
    visitor_id: str,
    user_id: str,
    conversation_id: str,
    text: str,
    reply_text: str,
    turn_result: dict[str, Any],
    widget: WebChatWidgetConfig,
    active_store: WebChatStoreBackend,
    past_reply_ready: bool,
) -> str:
    """Advance durable → capture → billing → complete and return the visitor-visible reply."""
    if not past_reply_ready:
        visible = _replay_if_operation_visible(
            runtime=runtime,
            credit=credit,
            tid=tid,
            operation_key=operation_key,
            reply_text=reply_text,
        )
        if visible is not None:
            return visible

    refresh_operation_runtime(runtime)
    current_state = runtime.record.state if runtime.record else None

    if current_state == OperationState.COMPLETE:
        replay = runtime.record.canonical_reply() if runtime.record else None
        if replay:
            return replay_complete_with_turn_repair(
                runtime=runtime,
                active_store=active_store,
                visitor_id=visitor_id,
                user_text=text,
                operation_key=operation_key,
                reply_text=replay,
            )

    if current_state == OperationState.CAPTURED:
        return complete_captured_turn(
            runtime=runtime,
            active_store=active_store,
            visitor_id=visitor_id,
            user_text=text,
            operation_key=operation_key,
            turn_result=turn_result,
            reply_text=reply_text,
        )

    if current_state == OperationState.BILLING_PENDING:
        reconciled = reconcile_billing_pending(tenant_id=tid, operation_key=operation_key, credit=credit)
        refresh_operation_runtime(runtime)
        if reconciled and reconciled.state == OperationState.COMPLETE:
            replay = reconciled.canonical_reply() or reply_text
            return replay_complete_with_turn_repair(
                runtime=runtime,
                active_store=active_store,
                visitor_id=visitor_id,
                user_text=text,
                operation_key=operation_key,
                reply_text=replay,
            )
        raise WebChatError("credit_capture_failed", "Could not finalize credits.", status_code=503)

    if current_state == OperationState.REPLY_READY:
        try:
            await _persist_web_turn(
                tenant_id=tid,
                user_id=user_id,
                conversation_id=conversation_id,
                visitor_id=visitor_id,
                user_text=text,
                reply_text=reply_text,
                widget=widget,
            )
        except WebChatError:
            fenced_failure_release(runtime, credit)
            raise
        _, won_durable = try_advance_operation(
            runtime,
            OperationState.REPLY_READY,
            OperationState.DURABLE_VISIBLE,
            result=turn_result,
        )
        if not won_durable:
            return _replay_or_raise(
                runtime=runtime,
                credit=credit,
                tid=tid,
                operation_key=operation_key,
                reply_text=reply_text,
                error_code="operation_in_progress",
                error_message="Operation durable stage in progress.",
            )
        credit.operation_state = OperationState.DURABLE_VISIBLE
        current_state = OperationState.DURABLE_VISIBLE

    refresh_operation_runtime(runtime)
    current_state = runtime.record.state if runtime.record else current_state

    if current_state == OperationState.COMPLETE:
        replay = runtime.record.canonical_reply() if runtime.record else None
        if replay:
            return replay_complete_with_turn_repair(
                runtime=runtime,
                active_store=active_store,
                visitor_id=visitor_id,
                user_text=text,
                operation_key=operation_key,
                reply_text=replay,
            )

    if current_state == OperationState.CAPTURED:
        return complete_captured_turn(
            runtime=runtime,
            active_store=active_store,
            visitor_id=visitor_id,
            user_text=text,
            operation_key=operation_key,
            turn_result=turn_result,
            reply_text=reply_text,
        )

    if current_state == OperationState.BILLING_PENDING:
        reconciled = reconcile_billing_pending(tenant_id=tid, operation_key=operation_key, credit=credit)
        refresh_operation_runtime(runtime)
        if reconciled and reconciled.state == OperationState.COMPLETE:
            replay = reconciled.canonical_reply() or reply_text
            return replay_complete_with_turn_repair(
                runtime=runtime,
                active_store=active_store,
                visitor_id=visitor_id,
                user_text=text,
                operation_key=operation_key,
                reply_text=replay,
            )
        raise WebChatError("credit_capture_failed", "Could not finalize credits.", status_code=503)

    if current_state == OperationState.DURABLE_VISIBLE:
        await _capture_then_mark_captured(
            runtime=runtime,
            credit=credit,
            turn_result=turn_result,
            tid=tid,
            operation_key=operation_key,
            reply_text=reply_text,
        )

    refresh_operation_runtime(runtime)
    current_state = runtime.record.state if runtime.record else current_state
    if current_state in {OperationState.CAPTURED, OperationState.COMPLETE}:
        if current_state == OperationState.COMPLETE:
            return replay_complete_with_turn_repair(
                runtime=runtime,
                active_store=active_store,
                visitor_id=visitor_id,
                user_text=text,
                operation_key=operation_key,
                reply_text=reply_text,
            )
        reply = complete_captured_turn(
            runtime=runtime,
            active_store=active_store,
            visitor_id=visitor_id,
            user_text=text,
            operation_key=operation_key,
            turn_result=turn_result,
            reply_text=reply_text,
        )
        _schedule_turn_followup(
            tid=tid,
            user_id=user_id,
            visitor_id=visitor_id,
            conversation_id=conversation_id,
            widget=widget,
        )
        return reply

    return reply_text
