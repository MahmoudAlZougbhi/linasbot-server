"""Run a combine_flush job: drain Redis buffer and execute one AI turn."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from services.queues.handlers import JobNotReady, PermanentJobError
from services.queues.models import QueueJob


async def handle_combine_flush(job: QueueJob) -> dict[str, Any]:
    from services.scale.message_combine_store import current_due, drain_if_due, load_context

    user_key = str((job.payload or {}).get("user_key") or "").strip()
    if not user_key:
        raise PermanentJobError("combine_flush_missing_user_key")
    due_at = current_due(user_key)
    now = time.time()
    if due_at > now + 0.02:
        raise JobNotReady("combine_not_due")
    chunks = drain_if_due(user_key, now=now)
    if chunks is None:
        raise JobNotReady("combine_not_due")
    if not chunks:
        return {"skipped": True, "reason": "empty_buffer"}
    context = load_context(user_key)
    texts = [str(item.get("text") or "") for item in chunks if str(item.get("text") or "").strip()]
    if not texts:
        return {"skipped": True, "reason": "empty_text"}
    event_ids = [str(item.get("event_id") or "") for item in chunks if str(item.get("event_id") or "")]
    trace_id = str((job.payload or {}).get("trace_id") or context.get("trace_id") or "")
    if trace_id:
        from services.scale.trace_context import set_trace_id
        from services.scale.trace_span import mark

        set_trace_id(trace_id)
        mark(trace_id, "worker_started")
        mark(trace_id, "ai_started")
    outcome = await _run_ai_turn(user_key, texts, context, event_ids, trace_id=trace_id)
    if event_ids:
        _mark_inbound_batch(event_ids, outcome)
    return {"ok": True, "chunks": len(chunks), "event_ids": event_ids, "outcome": outcome}


async def _run_ai_turn(
    user_key: str,
    texts: list[str],
    context: dict[str, Any],
    event_ids: list[str],
    *,
    trace_id: str,
) -> dict[str, Any]:
    import config
    from handlers.text_handlers_delayed import _delayed_process_messages

    channel = str(context.get("channel") or "").strip().lower()
    user_data = _user_data_for(user_key, context, event_ids, trace_id)
    config.user_pending_messages[user_key] = deque(texts)
    send_message, send_action = await _send_pair(user_key, user_data, context, channel)
    try:
        await _delayed_process_messages(
            user_key,
            user_data,
            send_message,
            send_action,
            combine_delay_seconds=0.0,
        )
        from services.scale.conversation_session import persist_from_process

        persist_from_process(user_key)
    finally:
        closer = user_data.pop("_combine_adapter_close", None)
        if closer is not None:
            await closer()
    from services.ai_reply_turn_runtime import finalize_delivery

    return finalize_delivery({"user_data": user_data})


def _user_data_for(user_key: str, context: dict[str, Any], event_ids: list[str], trace_id: str) -> dict[str, Any]:
    import config
    from services.scale.conversation_session import hydrate_into_process

    if user_key not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_key] = {
            "user_preferred_lang": "ar",
            "initial_user_query_to_process": None,
            "awaiting_human_handover_confirmation": False,
            "current_conversation_id": None,
            **config.DEFAULT_CONVERSATION_STATE,
        }
    user_data = hydrate_into_process(user_key)
    user_data["channel"] = str(context.get("channel") or user_data.get("channel") or "")
    user_data["tenant_id"] = str(context.get("tenant_id") or user_data.get("tenant_id") or "")
    user_data["meta_binding_id"] = str(context.get("binding_id") or user_data.get("meta_binding_id") or "")
    user_data["social_sender_id"] = str(context.get("sender_id") or user_data.get("social_sender_id") or "")
    user_data["phone_number"] = str(context.get("phone_number") or user_data.get("phone_number") or "")
    if event_ids:
        user_data["_inbound_event_id"] = event_ids[-1]
    if trace_id:
        user_data["_linas_trace_id"] = trace_id
        user_data["_ai_turn_trace_id"] = trace_id
    name = str(context.get("user_name") or "").strip()
    if name:
        config.user_names[user_key] = name
    return user_data


async def _send_pair(
    user_key: str,
    user_data: dict[str, Any],
    context: dict[str, Any],
    channel: str,
) -> tuple[Any, Any]:
    if channel in {"facebook", "instagram"}:
        return await _meta_send_pair(user_key, user_data, context, channel)
    if channel == "whatsapp":
        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        from services.whatsapp_adapters import WhatsAppFactory

        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())

        async def send_message(
            to_number: str,
            message_text: str | None = None,
            image_url: str | None = None,
            audio_url: str | None = None,
        ) -> Any:
            if message_text:
                return await adapter.send_text_message(to_number, message_text)
            if image_url:
                return await adapter.send_image_message(to_number, image_url)
            if audio_url:
                return await adapter.send_audio_message(to_number, audio_url)
            return False

        return send_message, send_whatsapp_typing_indicator
    raise PermanentJobError(f"combine_flush_unsupported_channel:{channel or 'unknown'}")


async def _meta_send_pair(
    user_key: str,
    user_data: dict[str, Any],
    context: dict[str, Any],
    channel: str,
) -> tuple[Any, Any]:
    from services.meta_messaging import MetaMessagingAdapter, resolve_meta_send_account_id
    from services.queues.meta_inbound_handler import _settings_from_snapshot
    from services.scale.inbound_event_store import get_inbound_event

    event_id = str(context.get("inbound_event_id") or user_data.get("_inbound_event_id") or "")
    rec = get_inbound_event(event_id) if event_id else None
    if rec is None:
        raise RuntimeError("combine_flush_inbound_missing")
    settings = _settings_from_snapshot(rec.settings_snapshot, rec.binding_snapshot)
    sender_id = str(context.get("sender_id") or rec.payload.get("sender_id") or "")
    account_id = resolve_meta_send_account_id(channel, rec.payload, settings)
    adapter = MetaMessagingAdapter(
        access_token=settings.page_access_token,
        account_id=account_id,
        channel=channel,
        graph_api_version=settings.graph_api_version,
        graph_base_url=settings.graph_base_url,
    )
    user_data["_combine_adapter_close"] = adapter.close
    binding_id = str(context.get("binding_id") or rec.binding_snapshot.get("binding_id") or "")

    async def send_message(
        _namespaced_id: str,
        message_text: str | None = None,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> Any:
        from services.meta_social_text_send import send_meta_social_outbound

        return await send_meta_social_outbound(
            namespaced_id=_namespaced_id,
            message_text=message_text,
            image_url=image_url,
            audio_url=audio_url,
            capture_send=None,
            adapter=adapter,
            inbound_event_id=event_id,
            channel=channel,
            binding_id=binding_id,
            sender_id=sender_id,
            user_data=user_data,
        )

    async def send_action(_namespaced_id: str) -> Any:
        return await adapter.send_typing(sender_id)

    from services.ai_reply_delivery import wrap_tracked_send

    return wrap_tracked_send(send_message, user_data), send_action


def _mark_inbound_batch(event_ids: list[str], outcome: dict[str, Any]) -> None:
    from services.scale.inbound_event_store import mark_inbound_state

    delivery = str(outcome.get("delivery") or "unknown")
    persisted = bool(outcome.get("logical_reply_id"))
    for event_id in event_ids:
        try:
            mark_inbound_state(
                event_id,
                state="completed",
                outbound_status=delivery,
                ai_output_persisted=persisted,
            )
        except Exception:
            continue
