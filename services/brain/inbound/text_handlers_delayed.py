from __future__ import annotations

# services/brain/inbound/text_handlers_delayed.py
# Delayed burst flush: combine rapid DMs, then one Terra turn.
import asyncio
import datetime
import hashlib
import uuid
from typing import Any

import config
from services.brain.inbound.burst_buffer import begin_flush, drain_burst_text, end_flush, log_flush, sleep_seconds
from services.brain.inbound.text_handlers_delayed_errors import (
    handle_delayed_process_exception,
    notify_empty_dashboard_queue,
)
from services.brain.inbound.text_handlers_respond import _process_and_respond
from services.scale.message_combine_policy import combine_delay_seconds as policy_delay
from services.scale.outbound_turn_idempotency import stable_ai_claim_identity, try_claim_ai_turn


async def _delayed_process_messages(
    user_id: str,
    user_data: dict,
    send_message_func: Any,
    send_action_func: Any,
    combine_delay_seconds: float | None = None,
    text_turn_epoch: int | None = None,
) -> Any:
    """Wait for a quiet window, drain the burst, run one customer AI turn."""
    try:
        user_data["_ai_turn_trace_id"] = str(user_data.get("_linas_trace_id") or uuid.uuid4())
        trace = user_data["_ai_turn_trace_id"]
        outbound_send = _guarded_send(send_message_func, user_id, user_data, text_turn_epoch, str(trace))
        from services.brain.ai_reply.ai_reply_delivery import wrap_tracked_send

        outbound_send = wrap_tracked_send(outbound_send, user_data)
        try:
            await send_action_func(user_id)
        except Exception as typing_error:
            channel = str(user_data.get("channel") or "unknown").strip().lower()
            print(f"[typing-indicator] send failed; continuing channel={channel} type={type(typing_error).__name__}")
        wait = sleep_seconds(
            quiet=policy_delay(combine_delay_seconds),
            started_at=user_data.get("_burst_started_at"),
        )
        if wait > 0:
            await asyncio.sleep(wait)
        if not begin_flush(user_id):
            log_flush(user_id, reason="skip_parallel", chunk_count=0)
            return
        try:
            combined_message, reason, chunk_count = drain_burst_text(user_id, user_data)
            log_flush(
                user_id,
                reason=reason,
                chunk_count=chunk_count,
                has_media=bool(user_data.get("user_image_base64") or user_data.get("inbound_attachment_types")),
            )
            if reason == "superseded":
                user_data["_combine_outcome"] = "superseded"
                return
            if combined_message:
                await _run_combined_turn(
                    user_id=user_id,
                    user_data=user_data,
                    combined_message=combined_message,
                    outbound_send=outbound_send,
                    send_action_func=send_action_func,
                    trace=str(trace),
                )
            else:
                await notify_empty_dashboard_queue(
                    user_id=user_id,
                    user_data=user_data,
                    outbound_send=outbound_send,
                )
            from services.scale.conversation_session import persist_from_process

            persist_from_process(user_id)
        finally:
            user_data.pop("_burst_started_at", None)
            end_flush(user_id)
            await _arm_local_followup(
                user_id=user_id,
                user_data=user_data,
                send_message_func=send_message_func,
                send_action_func=send_action_func,
                combine_delay_seconds=combine_delay_seconds,
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await handle_delayed_process_exception(
            exc=exc,
            user_id=user_id,
            user_data=user_data,
            outbound_send=locals().get("outbound_send", send_message_func),
        )
        raise


def _guarded_send(
    send_message_func: Any, user_id: str, user_data: dict, text_turn_epoch: int | None, trace: str
) -> Any:
    if text_turn_epoch is None:
        return send_message_func
    _raw_send = send_message_func

    async def _wrapped(
        to_number: str,
        message_text: str | None = None,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> Any:
        latest = user_data.get("_text_turn_epoch", 0)
        if text_turn_epoch < latest:
            print(
                f"⚠️ [text-turn] trace_id={trace} send=STALE_SKIP "
                f"epoch={text_turn_epoch} latest={latest} user={user_id[:16]}…"
            )
            return {"success": True, "skipped_stale_text_turn": True}
        return await _raw_send(
            to_number,
            message_text=message_text,
            image_url=image_url,
            audio_url=audio_url,
        )

    return _wrapped


async def _run_combined_turn(
    *,
    user_id: str,
    user_data: dict,
    combined_message: str,
    outbound_send: Any,
    send_action_func: Any,
    trace: str,
) -> None:
    try:
        mids = user_data.pop("_batch_inbound_mids", []) or []
        bfps = user_data.pop("_batch_turn_body_fps", []) or []
        if not isinstance(mids, list):
            mids = []
        if not mids:
            extra_events = [
                str(item).strip() for item in (user_data.get("_combine_event_ids") or []) if str(item).strip()
            ]
            inbound_one = str(user_data.get("_inbound_event_id") or "").strip()
            mids = extra_events or ([inbound_one] if inbound_one else [])
        claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
        from services.brain.ai_reply.ai_reply_turn_runtime import (
            ensure_turn_started,
            finalize_delivery,
            on_ai_failed,
            pending_delivery_for_claim,
            reset_turn_runtime_state,
            retry_saved_reply_delivery,
            settle_after_outbound,
            try_reserve_for_ai,
        )
        from services.scale.outbound_turn_idempotency import _claim_key_basis

        key_basis = _claim_key_basis(claim_id, mids, bfps) if (mids or bfps) else ""
        reset_turn_runtime_state(user_data)
        pending = pending_delivery_for_claim(key_basis) if key_basis else None
        if pending:
            user_data["_logical_reply_id"] = str(pending["logical_reply_id"])
            user_data["_ai_turn_started"] = True
            delivered = await retry_saved_reply_delivery(
                user_data=user_data,
                send_message_func=outbound_send,
                user_id=user_id,
                pending=pending,
            )
            finalize_delivery({"user_data": user_data})
            print(f"[ai-turn] trace_id={trace} delivery_retry={'DELIVERED' if delivered else 'FAILED'} saved_reply")
            return
        external_turn_id = f"claim:{hashlib.sha256(key_basis.encode()).hexdigest()}" if key_basis else None
        ensure_turn_started(user_data, claim_key_basis=key_basis or None, external_inbound_id=external_turn_id)
        if (mids or bfps) and not await try_claim_ai_turn(
            claim_id,
            mids,
            inbound_body_fps=bfps,
            binding_id=str(user_data.get("meta_binding_id") or ""),
            inbound_event_id=str(user_data.get("_inbound_event_id") or ""),
        ):
            print(
                f"⚠️ [ai-turn] trace_id={trace} claim=DUPLICATE_SKIP "
                f"user={user_id[:20]}… mids={len(mids)} bfps={len(bfps)} claim_key={claim_id[:16]}…"
            )
            return
        if not try_reserve_for_ai(user_data):
            print(f"[ai-turn] trace_id={trace} credit=BLOCKED — no customer reply")
            return
        print(
            f"[ai-turn] trace_id={trace} claim={'OK' if (mids or bfps) else 'SKIPPED(no_mids_no_bodyfp)'} "
            f"combined_len={len(combined_message or '')}"
        )
        try:
            try:
                import time as _time

                from services.scale.latency_histogram import observe
                from services.scale.trace_span import mark

                mark(str(trace), "ai_started")
                _ai_t0 = _time.time()
            except Exception:
                _ai_t0 = None
            await _process_and_respond(
                user_id,
                user_name=config.user_names.get(user_id, "عميل"),
                user_input_to_process=combined_message,
                user_data=user_data,
                send_message_func=outbound_send,
                send_action_func=send_action_func,
            )
            if _ai_t0 is not None:
                try:
                    mark(str(trace), "ai_finished")
                    observe("ai_ms", max(0.0, (_time.time() - _ai_t0) * 1000.0))
                except Exception:
                    pass
            delivery_summary = finalize_delivery({"user_data": user_data})
            if delivery_summary.get("delivery") != "delivered" and key_basis:
                from services.scale.outbound_turn_idempotency import release_ai_turn_claim

                await release_ai_turn_claim(key_basis)
            elif delivery_summary.get("delivery") == "delivered" and key_basis:
                from services.scale.outbound_turn_idempotency import complete_ai_turn_claim

                await complete_ai_turn_claim(key_basis)
        finally:
            if not user_data.get("_credit_captured_for_turn"):
                settle_after_outbound(user_data)
                if not user_data.get("_credit_captured_for_turn") and not user_data.get("_reply_ready"):
                    on_ai_failed({"user_data": user_data})
    finally:
        user_data.pop("_dashboard_test_turn_sticky", None)
    config.user_last_bot_response_time[user_id] = datetime.datetime.now()


async def _arm_local_followup(
    *,
    user_id: str,
    user_data: dict,
    send_message_func: Any,
    send_action_func: Any,
    combine_delay_seconds: float | None,
) -> None:
    from services.brain.inbound.burst_buffer import peek_has_pending
    from services.scale.message_combine_policy import durable_flush_jobs_enabled

    if durable_flush_jobs_enabled() or not peek_has_pending(user_id):
        return
    from services.brain.inbound.text_handlers_combine import arm_followup_flush

    await arm_followup_flush(
        user_id=user_id,
        user_data=user_data,
        send_message_func=send_message_func,
        send_action_func=send_action_func,
        message_combine_delay=combine_delay_seconds,
    )
