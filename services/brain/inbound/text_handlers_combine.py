"""Schedule combined-message processing: Redis buffer + optional delayed flush job."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import config
from services.brain.inbound.burst_buffer import is_flushing, log_flush, sleep_seconds
from services.brain.inbound.text_handlers_firestore import _delayed_processing_tasks


async def schedule_combined_turn(
    *,
    user_id: str,
    raw_msg: str,
    user_data: dict[str, Any],
    send_message_func: Any,
    send_action_func: Any,
    message_combine_delay: float | None,
) -> None:
    from services.scale.message_combine_policy import combine_delay_seconds
    from services.scale.message_combine_store import append_chunk, save_context

    delay = combine_delay_seconds(message_combine_delay)
    event_id = str(user_data.get("_inbound_event_id") or "")
    mid = str(user_data.get("_combine_mid") or user_data.get("_source_message_id") or "")
    trace_id = str(user_data.get("_linas_trace_id") or user_data.get("_ai_turn_trace_id") or "")
    append_result = append_chunk(
        user_id,
        text=raw_msg,
        event_id=event_id,
        mid=mid,
        trace_id=trace_id,
        delay_seconds=delay,
    )
    generation = int(append_result.get("generation") or 0)
    user_data["_combine_generation"] = generation
    if not append_result.get("redis"):
        config.user_pending_messages[user_id].append(raw_msg)
    save_context(
        user_id,
        {
            "tenant_id": str(user_data.get("tenant_id") or ""),
            "channel": str(user_data.get("channel") or ""),
            "binding_id": str(user_data.get("meta_binding_id") or ""),
            "sender_id": str(user_data.get("social_sender_id") or ""),
            "inbound_event_id": event_id,
            "trace_id": trace_id,
            "conversation_key": str(user_data.get("_conversation_key") or ""),
            "user_name": str(config.user_names.get(user_id) or ""),
            "phone_number": str(user_data.get("phone_number") or ""),
        },
    )
    if append_result.get("duplicate"):
        return
    if user_data.get("_dashboard_test_simulation"):
        user_data["_dashboard_last_message_for_fallback"] = raw_msg
        user_data["_dashboard_test_turn_sticky"] = raw_msg
        if append_result.get("redis"):
            config.user_pending_messages[user_id].append(raw_msg)
    if is_flushing(user_id):
        log_flush(user_id, reason="held_inflight", extra=f"generation={generation}")
        await _schedule_durable_bump(user_id, user_data, append_result, delay, trace_id, generation)
        return
    if not user_data.get("_burst_started_at"):
        user_data["_burst_started_at"] = time.time()
    await _arm_flush(
        user_id=user_id,
        user_data=user_data,
        send_message_func=send_message_func,
        send_action_func=send_action_func,
        message_combine_delay=message_combine_delay,
        delay=delay,
        append_result=append_result,
        trace_id=trace_id,
        generation=generation,
        cancel_other=True,
    )


async def arm_followup_flush(
    *,
    user_id: str,
    user_data: dict[str, Any],
    send_message_func: Any,
    send_action_func: Any,
    message_combine_delay: float | None,
) -> None:
    """Quiet-window flush for chunks that arrived while Terra was already running."""
    from services.scale.message_combine_policy import combine_delay_seconds

    delay = combine_delay_seconds(message_combine_delay)
    user_data["_burst_started_at"] = time.time()
    await _arm_flush(
        user_id=user_id,
        user_data=user_data,
        send_message_func=send_message_func,
        send_action_func=send_action_func,
        message_combine_delay=message_combine_delay,
        delay=delay,
        append_result={"due_at": time.time() + delay, "duplicate": False},
        trace_id=str(user_data.get("_linas_trace_id") or ""),
        generation=int(user_data.get("_combine_generation") or 0),
        cancel_other=False,
    )


async def _arm_flush(
    *,
    user_id: str,
    user_data: dict[str, Any],
    send_message_func: Any,
    send_action_func: Any,
    message_combine_delay: float | None,
    delay: float,
    append_result: dict[str, Any],
    trace_id: str,
    generation: int,
    cancel_other: bool,
) -> None:
    from services.brain.inbound.text_handlers_message import _delayed_process_messages

    wait = sleep_seconds(quiet=delay, started_at=user_data.get("_burst_started_at"))
    existing = _delayed_processing_tasks.get(user_id)
    me = asyncio.current_task()
    if cancel_other and existing is not None and not existing.done() and existing is not me:
        existing.cancel()
    user_data["_text_turn_epoch"] = user_data.get("_text_turn_epoch", 0) + 1
    text_turn_epoch = user_data["_text_turn_epoch"]
    if user_data.get("_dashboard_test_simulation"):
        try:
            await _delayed_process_messages(
                user_id,
                user_data,
                send_message_func,
                send_action_func,
                combine_delay_seconds=message_combine_delay,
                text_turn_epoch=text_turn_epoch,
            )
        finally:
            _delayed_processing_tasks.pop(user_id, None)
        return
    if await _schedule_durable_bump(user_id, user_data, append_result, delay, trace_id, generation):
        return
    _delayed_processing_tasks[user_id] = asyncio.create_task(
        _delayed_process_messages(
            user_id,
            user_data,
            send_message_func,
            send_action_func,
            combine_delay_seconds=wait,
            text_turn_epoch=text_turn_epoch,
        )
    )


async def _schedule_durable_bump(
    user_id: str,
    user_data: dict[str, Any],
    append_result: dict[str, Any],
    delay: float,
    trace_id: str,
    generation: int,
) -> bool:
    from services.scale.message_combine_policy import durable_flush_jobs_enabled
    from services.scale.message_combine_schedule import schedule_combine_flush

    if not (durable_flush_jobs_enabled() and delay > 0 and not append_result.get("duplicate")):
        return False
    due_at = float(append_result.get("due_at") or 0.0)
    tenant_id = str(user_data.get("tenant_id") or "")
    conversation_key = str(
        user_data.get("_conversation_key") or f"{tenant_id}:{user_data.get('channel') or 'unknown'}:{user_id}"
    )
    schedule_combine_flush(
        user_key=user_id,
        tenant_id=tenant_id,
        conversation_key=conversation_key,
        due_at=due_at,
        payload={
            "channel": str(user_data.get("channel") or ""),
            "trace_id": trace_id,
            "generation": generation,
            "binding_id": str(user_data.get("meta_binding_id") or ""),
        },
    )
    user_data["_distributed_combine_scheduled"] = True
    import logging

    logging.getLogger("uvicorn.error").info(
        "[meta-combine] scheduled user_key=%s generation=%s due_at=%.3f binding=%s channel=%s",
        user_id[:80],
        generation,
        due_at,
        str(user_data.get("meta_binding_id") or "")[:12],
        str(user_data.get("channel") or ""),
    )
    from services.scale.conversation_session import persist_from_process

    persist_from_process(user_id)
    return True
