"""Honest Live Chat operator delivery_status: persist + SSE (HA Redis fanout)."""

from __future__ import annotations

import uuid
from typing import Any

from services.live_chat_channel import resolve_live_chat_channel
from services.live_chat_contracts import utc_now
from services.live_chat_operator_pause_session import operator_thread_status

APP_ID = "linas-ai-bot-backend"


def compose_operator_text_result(
    delivery: dict[str, Any],
    manual_meta: dict[str, Any],
    *,
    client_message_id: str | None = None,
) -> dict[str, Any]:
    payload = {**manual_meta, **(delivery or {})}
    success = bool(payload.get("success"))
    delivered = bool(payload.get("delivered"))
    queued = bool(payload.get("queued")) and success and not delivered
    if success:
        delivery_status = "sent" if delivered and not queued else "sending"
    else:
        delivery_status = "failed"
        queued = False
    payload["success"] = success
    payload["delivered"] = delivered
    payload["queued"] = queued
    payload["delivery_status"] = str(payload.get("delivery_status") or delivery_status)
    if client_message_id:
        payload["client_message_id"] = client_message_id
    if success:
        payload["status"] = operator_thread_status(paused=True)
        if queued:
            payload["message"] = "Message accepted"
        else:
            payload.setdefault("message", "Message sent successfully")
    return payload


async def publish_operator_delivery_status(
    *,
    user_id: str,
    conversation_id: str,
    delivery_status: str,
    client_message_id: str | None = None,
    message_id: str | None = None,
    error: str | None = None,
    provider_message_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    from modules.live_chat_api_helpers import broadcast_sse_event

    uid = str(user_id or "").strip()
    if not uid:
        return
    channel = resolve_live_chat_channel(uid)
    data: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "event_ts": utc_now().isoformat(),
        "user_id": uid,
        "conversation_id": conversation_id,
        "channel": channel,
        "delivery_status": delivery_status,
        "client_message_id": client_message_id,
        "client_send_id": client_message_id,
        "message_id": message_id,
        "provider_message_id": provider_message_id,
        "error": (str(error)[:180] if error else None),
    }
    if tenant_id:
        data["tenant_id"] = tenant_id
    await broadcast_sse_event("message_status", {k: v for k, v in data.items() if v not in (None, "")})


async def persist_operator_delivery_status(
    *,
    user_id: str,
    conversation_id: str,
    client_message_id: str | None,
    delivery_status: str,
    error: str | None = None,
    provider_message_id: str | None = None,
) -> None:
    """Patch the matching operator bubble. Missing Firestore is skipped, never faked."""
    key = str(client_message_id or "").strip()
    if not key or not conversation_id:
        return
    try:
        import asyncio

        from utils.utils import get_canonical_user_id_and_phone, get_firestore_db

        db = get_firestore_db()
        if not db:
            return
        canonical, _ = get_canonical_user_id_and_phone(user_id)
        ref = (
            db.collection("artifacts")
            .document(APP_ID)
            .collection("users")
            .document(canonical)
            .collection("conversations")
            .document(conversation_id)
        )

        def _patch() -> None:
            snap = ref.get()
            if not getattr(snap, "exists", False):
                return
            data = snap.to_dict() or {}
            messages = list(data.get("messages") or [])
            changed = False
            for msg in reversed(messages):
                if not isinstance(msg, dict):
                    continue
                meta = dict(msg.get("metadata") or {})
                candidates = {
                    str(meta.get("client_message_id") or ""),
                    str(msg.get("client_message_id") or ""),
                    str(msg.get("message_id") or ""),
                    str(meta.get("message_id") or ""),
                }
                if key not in candidates:
                    continue
                meta["delivery_status"] = delivery_status
                if error:
                    meta["delivery_error"] = str(error)[:180]
                else:
                    meta.pop("delivery_error", None)
                if provider_message_id:
                    meta["provider_message_id"] = str(provider_message_id)[:128]
                msg["metadata"] = meta
                msg["delivery_status"] = delivery_status
                changed = True
                break
            if changed:
                ref.update({"messages": messages})

        await asyncio.to_thread(_patch)
    except Exception as exc:
        print(f"⚠️ persist operator delivery_status failed: {exc}")


async def finalize_operator_delivery_state(
    *,
    user_id: str,
    conversation_id: str,
    client_message_id: str | None,
    delivery_status: str,
    error: str | None = None,
    provider_message_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    await persist_operator_delivery_status(
        user_id=user_id,
        conversation_id=conversation_id,
        client_message_id=client_message_id,
        delivery_status=delivery_status,
        error=error,
        provider_message_id=provider_message_id,
    )
    await publish_operator_delivery_status(
        user_id=user_id,
        conversation_id=conversation_id,
        delivery_status=delivery_status,
        client_message_id=client_message_id,
        error=error,
        provider_message_id=provider_message_id,
        tenant_id=tenant_id,
    )


async def notify_live_chat_operator_job(
    payload: dict[str, Any] | None,
    *,
    delivery_status: str,
    error: str | None = None,
    provider_message_id: str | None = None,
) -> None:
    data = payload or {}
    user_id = str(data.get("live_chat_user_id") or "").strip()
    if not user_id:
        return
    client_id = str(data.get("live_chat_client_message_id") or "").strip() or None
    await finalize_operator_delivery_state(
        user_id=user_id,
        conversation_id=str(data.get("live_chat_conversation_id") or ""),
        client_message_id=client_id,
        delivery_status=delivery_status,
        error=error,
        provider_message_id=provider_message_id,
        tenant_id=str(data.get("tenant_id") or "") or None,
    )
    if delivery_status == "failed" and client_id:
        from services.live_chat_service_common import release_operator_send_idempotency

        await release_operator_send_idempotency(client_id)
