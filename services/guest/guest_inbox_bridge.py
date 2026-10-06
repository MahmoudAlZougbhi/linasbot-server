"""Project a public guest session into that tenant's Live Chat inbox."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from urllib.parse import urlparse

from services.guest.guest_chat_store import GuestSession

_log = logging.getLogger(__name__)


def guest_user_id(session_id: str) -> str:
    return f"web:{session_id}"


def guest_conversation_id(tenant_id: str, session_id: str) -> str:
    return f"web:{tenant_id}:{session_id}"


def live_token_for(session_id: str, *, key: str) -> str:
    return hmac.new(key.encode("utf-8"), session_id.encode("utf-8"), hashlib.sha256).hexdigest()


def live_token_matches(session_id: str, token: str, *, key: str) -> bool:
    expected = live_token_for(session_id, key=key)
    presented = (token or "").strip()
    return bool(presented) and hmac.compare_digest(expected, presented)


def guest_live_key() -> str:
    import hashlib
    import hmac
    import os

    explicit = (os.getenv("LINAS_GUEST_LIVE_KEY") or "").strip()
    if explicit:
        return explicit
    from services.dashboard.dashboard_session_service import get_auth_secret

    secret = get_auth_secret()
    return hmac.new(secret.encode("utf-8"), b"linas-guest-live-v1", hashlib.sha256).hexdigest()


def _host(origin: str | None) -> str:
    text = (origin or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    return (urlparse(text).hostname or "").lower()


def resolve_guest_widget(origin: str | None) -> Any | None:
    """Pick the widget for this page. One installed widget is the page config."""
    try:
        from sqlalchemy import select

        from services.integrations.web_chat.ha_repository import with_ha_session
        from services.integrations.web_chat.pg_models import WebChatWidgetRow
        from services.integrations.web_chat.store_pg import _widget_from_row
    except Exception:
        return None
    try:
        with with_ha_session() as db:
            rows = list(db.scalars(select(WebChatWidgetRow)))
            widgets = [_widget_from_row(row) for row in rows]
    except Exception as exc:
        _log.info("guest widget lookup skipped: %s", type(exc).__name__)
        return None
    if not widgets:
        return None
    host = _host(origin)
    if host:
        for widget in widgets:
            site_host = _host(widget.site_url)
            if site_host and site_host == host:
                return widget
    if len(widgets) == 1:
        return widgets[0]
    return None


def _ensure_visitor(widget: Any, session_id: str, greeting: str, token: str) -> None:
    from services.integrations.web_chat.store import web_chat_store

    web_chat_store.get_or_create_visitor(
        session_id=session_id,
        widget=widget,
        greeting=greeting,
        authority_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )


def project_guest_message(
    *,
    tenant_id: str,
    session_id: str,
    role: str,
    text: str,
    message_id: str,
) -> None:
    from services.persistence.chat_store import append_message

    append_message(
        user_id=guest_user_id(session_id),
        role="user" if role == "user" else "ai",
        text_body=text,
        conversation_id=guest_conversation_id(tenant_id, session_id),
        metadata={
            "tenant_id": tenant_id,
            "channel": "web",
            "source": "guest_ai",
            "source_message_id": message_id,
            "message_id": message_id,
        },
        channel="web",
    )


def _operator_messages(tenant_id: str, session_id: str) -> list[dict[str, Any]]:
    from services.persistence.chat_store import list_messages

    rows = list_messages(tenant_id, guest_conversation_id(tenant_id, session_id), limit=100)
    found: list[dict[str, Any]] = []
    for row in reversed(rows):
        if str(row.get("role") or "") != "operator":
            continue
        found.append(
            {
                "id": str(row.get("message_id") or ""),
                "role": "assistant",
                "content": str(row.get("body") or ""),
                "created_at": _stamp(row.get("sent_at")),
            }
        )
    return found


def _stamp(value: Any) -> float:
    import datetime

    text = str(value or "")
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def projection_enabled() -> bool:
    import os

    flag = (os.getenv("LINAS_GUEST_INBOX") or "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    if flag in {"1", "true", "on", "yes"}:
        return True
    from config import is_production_runtime

    return is_production_runtime()


def publish_guest_view(session: GuestSession, *, origin: str | None) -> dict[str, Any]:
    """Copy the guest thread into the tenant inbox and return the public view."""
    token = live_token_for(session.id, key=guest_live_key())
    if not projection_enabled():
        messages = [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in session.messages
        ]
        return {"messages": messages, "live_token": token}
    messages = [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in session.messages
    ]
    try:
        widget = resolve_guest_widget(origin)
    except Exception as exc:
        _log.info("guest widget lookup skipped: %s", type(exc).__name__)
        widget = None
    if widget is None:
        return {"messages": messages, "live_token": token}
    tenant_id = str(widget.tenant_id or "").strip().lower()
    if not tenant_id:
        return {"messages": messages, "live_token": token}
    try:
        greeting = session.messages[0].content if session.messages else ""
        _ensure_visitor(widget, session.id, greeting, token)
        for message in session.messages:
            project_guest_message(
                tenant_id=tenant_id,
                session_id=session.id,
                role=message.role,
                text=message.content,
                message_id=message.id,
            )
        seen = {str(item["id"]) for item in messages}
        for extra in _operator_messages(tenant_id, session.id):
            if extra["id"] and extra["id"] not in seen:
                messages.append(extra)
    except Exception as exc:
        _log.info("guest inbox projection skipped: %s", type(exc).__name__)
    return {"messages": messages, "live_token": token, "tenant_id": tenant_id}
