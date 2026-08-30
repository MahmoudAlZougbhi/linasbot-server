"""Public Website Chat handlers: bootstrap, messages, poll, ack with session authority."""

from __future__ import annotations

from typing import Any

from services.web_chat.config_models import WebChatWidgetConfig, config_to_raw
from services.web_chat.delivery_outbox import ack_pending_messages, poll_pending_messages
from services.web_chat.flags import assert_widget_operational, web_chat_containment_active
from services.web_chat.processor import (
    WebChatError,
    default_greeting,
    evaluate_web_ai_eligibility,
    process_web_chat_message,
)
from services.web_chat.public_config import build_public_widget_config
from services.web_chat.session_authority import SessionAuthorityError, issue_session_authority
from services.web_chat.store import WebChatStoreBackend, web_chat_store


def reject_if_contained() -> None:
    if web_chat_containment_active():
        raise WebChatError("WEB_CHAT_UNAVAILABLE", "Website chat is not available.", status_code=503)


async def bootstrap_visitor_session(
    *,
    widget: WebChatWidgetConfig,
    language: str | None = None,
    store: WebChatStoreBackend | None = None,
) -> dict[str, Any]:
    reject_if_contained()
    assert_widget_operational(widget)
    active_store = store or web_chat_store
    bundle = issue_session_authority(widget=widget)
    greeting = default_greeting(language, widget)
    session = active_store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting=greeting,
        authority_hash=bundle.authority_hash,
    )
    eligible, _blocker = evaluate_web_ai_eligibility(widget.tenant_id, widget)
    return {
        "success": True,
        "session_id": session.id,
        "session_authority": bundle.authority_token,
        "channel": "web",
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in session.messages
        ],
        "ai_available": eligible,
        "config": build_public_widget_config(widget, eligible=eligible),
    }


async def send_visitor_message(
    *,
    widget: WebChatWidgetConfig,
    session_id: str,
    session_authority: str,
    content: str,
    store: WebChatStoreBackend | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    reject_if_contained()
    assert_widget_operational(widget)
    active_store = store or web_chat_store
    visitor = active_store.get_visitor(session_id)
    if visitor is None:
        raise SessionAuthorityError("SESSION_NOT_FOUND", "Visitor session not found.")
    if visitor.widget_key != widget.widget_key:
        raise SessionAuthorityError("SESSION_BOUNDARY", "Session does not belong to this widget.")
    from services.web_chat.session_authority import verify_session_binding

    if visitor.authority_hash:
        verify_session_binding(
            session_tenant_id=visitor.tenant_id,
            session_widget_key=visitor.widget_key,
            authority_hash=visitor.authority_hash,
            widget=widget,
            presented_authority=session_authority,
        )
    else:
        raise SessionAuthorityError("LEGACY_SESSION_REJECTED", "Legacy session must be re-bootstrapped.")

    try:
        from services.job_queue import job_queue
        from services.omnichannel.enqueue import AMBIGUOUS_ENQUEUE, enqueue_job, should_defer_to_worker

        if should_defer_to_worker():
            if idempotency_key and active_store.has_assistant_delivery(session_id, idempotency_key):
                refreshed = active_store.get_visitor(session_id)
                return {
                    "success": True,
                    "channel": "web",
                    "status": "duplicate",
                    "reply": "",
                    "messages": [
                        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
                        for m in (refreshed.messages if refreshed else [])
                    ],
                }
            if not getattr(job_queue, "production_ready", False):
                raise WebChatError("queue_unavailable", "Website chat is temporarily unavailable.", status_code=503)
            job_id = enqueue_job(
                logical_queue="web_chat",
                job_type="web_chat_generate",
                tenant_id=widget.tenant_id,
                payload={
                    "session_id": session_id,
                    "content": content,
                    "idempotency_key": idempotency_key,
                    "widget_dict": config_to_raw(widget),
                },
                idempotency_key=f"web:{session_id}:{idempotency_key or content[:40]}",
                conversation_key=session_id,
                provider="openai",
            )
            if job_id is None or job_id == AMBIGUOUS_ENQUEUE:
                raise WebChatError("queue_unavailable", "Website chat is temporarily unavailable.", status_code=503)
            refreshed = active_store.get_visitor(session_id)
            return {
                "success": True,
                "channel": "web",
                "status": "generating",
                "reply": "",
                "messages": [
                    {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
                    for m in (refreshed.messages if refreshed else [])
                ],
            }
        reply = await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text=content,
            store=active_store,
            idempotency_key=idempotency_key,
        )
    except WebChatError as exc:
        return {"success": False, "error": exc.code, "message": exc.message, "status_code": exc.status_code}
    refreshed = active_store.get_visitor(session_id)
    return {
        "success": True,
        "channel": "web",
        "reply": reply,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in (refreshed.messages if refreshed else [])
        ],
    }


def poll_messages(
    *,
    widget: WebChatWidgetConfig,
    session_id: str,
    session_authority: str,
    cursor: str | None = None,
    store: WebChatStoreBackend | None = None,
) -> dict[str, Any]:
    reject_if_contained()
    assert_widget_operational(widget)
    return poll_pending_messages(
        session_id=session_id,
        widget=widget,
        session_authority=session_authority,
        cursor=cursor,
        store=store,
    )


def ack_messages(
    *,
    widget: WebChatWidgetConfig,
    session_id: str,
    session_authority: str,
    message_ids: list[str],
    store: WebChatStoreBackend | None = None,
) -> dict[str, Any]:
    reject_if_contained()
    assert_widget_operational(widget)
    return ack_pending_messages(
        session_id=session_id,
        widget=widget,
        session_authority=session_authority,
        message_ids=message_ids,
        store=store,
    )
