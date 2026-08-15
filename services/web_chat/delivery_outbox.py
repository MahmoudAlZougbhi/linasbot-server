"""Browser-visible durable follow-up: poll cursor reads and acknowledgements."""

from __future__ import annotations

from typing import Any

from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.operation import mark_operation_delivery_acked
from services.web_chat.operation_fsm import stable_operation_key
from services.web_chat.session_authority import SessionAuthorityError, verify_session_binding
from services.web_chat.store import WebChatStoreBackend, WebChatVisitorSession, web_chat_store


def _message_payload(msg: Any) -> dict[str, Any]:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at,
    }


def _require_session(
    store: WebChatStoreBackend,
    *,
    session_id: str,
    widget: WebChatWidgetConfig,
    session_authority: str,
) -> WebChatVisitorSession:
    visitor = store.get_visitor(session_id)
    if visitor is None:
        raise SessionAuthorityError("SESSION_NOT_FOUND", "Visitor session not found.")
    if visitor.widget_key != widget.widget_key or visitor.tenant_id != widget.tenant_id:
        raise SessionAuthorityError("SESSION_BOUNDARY", "Session does not belong to this widget.")
    auth_hash = getattr(visitor, "authority_hash", "") or ""
    if not auth_hash:
        raise SessionAuthorityError("LEGACY_SESSION_REJECTED", "Legacy session must be re-bootstrapped.")
    verify_session_binding(
        session_tenant_id=visitor.tenant_id,
        session_widget_key=visitor.widget_key,
        authority_hash=auth_hash,
        widget=widget,
        presented_authority=session_authority,
    )
    return visitor


def poll_pending_messages(
    *,
    session_id: str,
    widget: WebChatWidgetConfig,
    session_authority: str,
    cursor: str | None = None,
    store: WebChatStoreBackend | None = None,
) -> dict[str, Any]:
    active_store = store or web_chat_store
    _require_session(active_store, session_id=session_id, widget=widget, session_authority=session_authority)
    pending, next_cursor = active_store.list_pending_since_cursor(session_id, cursor=cursor)
    messages = [_message_payload(m) for m in pending]
    return {"success": True, "messages": messages, "cursor": next_cursor}


def ack_pending_messages(
    *,
    session_id: str,
    widget: WebChatWidgetConfig,
    session_authority: str,
    message_ids: list[str],
    store: WebChatStoreBackend | None = None,
) -> dict[str, Any]:
    active_store = store or web_chat_store
    visitor = _require_session(active_store, session_id=session_id, widget=widget, session_authority=session_authority)

    ids = [str(mid).strip() for mid in (message_ids or []) if str(mid).strip()]
    acked = active_store.ack_assistant_messages(session_id, message_ids=ids)

    if acked:
        for message_id in ids:
            mark_operation_delivery_acked(
                tenant_id=visitor.tenant_id,
                operation_key=stable_operation_key(session_id=session_id, client_key=message_id),
            )

    return {"success": True, "acked": acked, "message_ids": ids}
