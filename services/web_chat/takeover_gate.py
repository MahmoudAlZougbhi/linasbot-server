"""Honor Live Chat human takeover for Web Chat AI (same Firestore epoch as WhatsApp)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from services.web_chat.constants import CHANNEL_ID, SOURCE_CHANNEL_WEB_CHAT
from services.web_chat.store import WebChatWidgetConfig


@dataclass(frozen=True)
class WebChatTakeoverState:
    active: bool
    operator_id: str | None


def _waiting_notice(lang: str = "ar") -> str:
    from services.dynamic_messages_service import get_dynamic_message

    return (
        get_dynamic_message("waiting_queue_message", lang)
        or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
    )


async def read_web_chat_takeover_state(*, user_id: str, conversation_id: str) -> WebChatTakeoverState:
    """Firestore human_takeover_active. Errors allow AI (WhatsApp parity)."""
    try:
        from utils.utils import get_canonical_user_id_and_phone, get_firestore_db

        db = get_firestore_db()
        if not db:
            return WebChatTakeoverState(active=False, operator_id=None)
        from handlers.text_handlers_message_takeover import resolve_conversation_doc_ref

        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
        users_coll = db.collection("artifacts").document("linas-ai-bot-backend").collection("users")
        _ref, snap, _resolved = await resolve_conversation_doc_ref(
            users_coll,
            conversation_id,
            canonical_user_id,
            user_id,
        )
        if snap is None or not getattr(snap, "exists", False):
            return WebChatTakeoverState(active=False, operator_id=None)
        data = snap.to_dict() or {}
        if not data.get("human_takeover_active"):
            return WebChatTakeoverState(active=False, operator_id=None)
        operator_id = str(data.get("operator_id") or "").strip() or None
        return WebChatTakeoverState(active=True, operator_id=operator_id)
    except Exception as exc:
        print(f"⚠️ Web Chat takeover check failed (AI allowed): {exc}")
        return WebChatTakeoverState(active=False, operator_id=None)


async def _persist_web_projection(
    *,
    user_id: str,
    conversation_id: str,
    role: str,
    text: str,
    widget: WebChatWidgetConfig,
    tenant_id: str,
    event: str,
) -> None:
    from services.web_chat.persistence import PersistFailure, PersistOutcome, persist_web_chat_message

    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    try:
        result = await persist_web_chat_message(
            user_id=user_id,
            role=role,
            text=text,
            conversation_id=conversation_id,
            metadata={
                "channel": CHANNEL_ID,
                "source": SOURCE_CHANNEL_WEB_CHAT,
                "widget_key": widget.widget_key,
                "tenant_id": tenant_id,
                "handled_by": "ai" if role == "ai" else "user",
                "event": event,
                "source_message_id": f"{role}:{conversation_id}:{digest}",
            },
        )
        if result.outcome not in {PersistOutcome.CREATED, PersistOutcome.DUPLICATE}:
            print(f"⚠️ Web Chat takeover persist {role} skipped: {result.outcome}")
    except PersistFailure as exc:
        print(f"⚠️ Web Chat takeover persist {role} failed: {exc}")


def _queue_waiting_notice(*, visitor_id: str, conversation_id: str, inbound_text: str, notice: str) -> bool:
    from services.web_chat.store import web_chat_store

    digest = hashlib.sha256(inbound_text.encode()).hexdigest()[:16]
    key = f"livechat-waiting:{conversation_id}:{digest}"
    try:
        queued = web_chat_store.queue_assistant_message(visitor_id, notice, idempotency_key=key)
    except Exception as exc:
        print(f"⚠️ Web Chat waiting-queue outbox failed (AI stays silent): {exc}")
        return False
    return queued is not False


async def maybe_silence_web_chat_for_takeover(
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
    visitor_id: str,
    inbound_text: str,
    widget: WebChatWidgetConfig,
) -> bool:
    """True when AI must not reply. Waiting queue notice is queued when no operator yet."""
    state = await read_web_chat_takeover_state(user_id=user_id, conversation_id=conversation_id)
    if not state.active:
        return False
    if state.operator_id:
        print(
            f"[web_chat] takeover assigned operator={state.operator_id}; skipping AI for "
            f"...{str(user_id)[-4:]}"
        )
        return True
    print(f"[web_chat] waiting queue; skipping AI for ...{str(user_id)[-4:]}")
    await _persist_web_projection(
        user_id=user_id,
        conversation_id=conversation_id,
        role="user",
        text=inbound_text,
        widget=widget,
        tenant_id=tenant_id,
        event="waiting_queue_inbound",
    )
    notice = _waiting_notice()
    queued = _queue_waiting_notice(
        visitor_id=visitor_id,
        conversation_id=conversation_id,
        inbound_text=inbound_text,
        notice=notice,
    )
    if queued:
        await _persist_web_projection(
            user_id=user_id,
            conversation_id=conversation_id,
            role="ai",
            text=notice,
            widget=widget,
            tenant_id=tenant_id,
            event="waiting_queue_autoreply",
        )
    return True
