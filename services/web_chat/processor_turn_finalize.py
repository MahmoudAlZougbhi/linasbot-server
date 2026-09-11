"""Canonical turn append + COMPLETE transition helpers for web chat turns."""

from __future__ import annotations

from typing import Any

from services.web_chat.operation import (
    OperationRuntime,
    abandon_operation_lease,
    refresh_operation_runtime,
    try_advance_operation,
)
from services.web_chat.operation_fsm import OperationState
from services.web_chat.processor import _ensure_turn_appended
from services.web_chat.store import WebChatStoreBackend


def canonical_reply_text(record: Any, fallback: str) -> str:
    return (record.canonical_reply() if record else None) or fallback


def repair_canonical_turn(
    *,
    active_store: WebChatStoreBackend,
    visitor_id: str,
    user_text: str,
    operation_key: str,
    canonical: str,
) -> None:
    _ensure_turn_appended(
        active_store,
        visitor_id,
        user_text=user_text,
        assistant_text=canonical,
        turn_key=operation_key,
    )


def replay_complete_with_turn_repair(
    *,
    runtime: OperationRuntime,
    active_store: WebChatStoreBackend,
    visitor_id: str,
    user_text: str,
    operation_key: str,
    reply_text: str,
) -> str:
    refresh_operation_runtime(runtime)
    record = runtime.record
    canonical = canonical_reply_text(record, reply_text)
    repair_canonical_turn(
        active_store=active_store,
        visitor_id=visitor_id,
        user_text=user_text,
        operation_key=operation_key,
        canonical=canonical,
    )
    return canonical


def complete_captured_turn(
    *,
    runtime: OperationRuntime,
    active_store: WebChatStoreBackend,
    visitor_id: str,
    user_text: str,
    operation_key: str,
    turn_result: dict[str, Any],
    reply_text: str,
) -> str:
    """Append canonical turn first, then advance CAPTURED → COMPLETE."""
    refresh_operation_runtime(runtime)
    record = runtime.record
    canonical = canonical_reply_text(record, reply_text)
    try:
        repair_canonical_turn(
            active_store=active_store,
            visitor_id=visitor_id,
            user_text=user_text,
            operation_key=operation_key,
            canonical=canonical,
        )
        if record and record.state == OperationState.CAPTURED:
            try_advance_operation(
                runtime,
                OperationState.CAPTURED,
                OperationState.COMPLETE,
                result=turn_result,
            )
    except Exception:
        try:
            abandon_operation_lease(runtime)
        except Exception:
            pass
        raise
    refresh_operation_runtime(runtime)
    from services.customer_ai.billing import settle_after_send
    from services.customer_ai.history_ids import web_inbound_message_id

    conversation_id = str((turn_result or {}).get("conversation_id") or "")
    web_mid = web_inbound_message_id(conversation_id, user_text) if conversation_id else ""
    settle_after_send(
        tenant_id=runtime.tenant_id,
        operation_id=web_mid or operation_key,
        accepted=True,
        channel="web_chat",
        extra_ids=(
            operation_key,
            str(getattr(runtime.record, "inbound_event_id", "") or ""),
            web_mid,
            conversation_id,
        ),
    )
    return canonical_reply_text(runtime.record, canonical)
