"""Live Chat API helpers and SSE broadcast (LOC split from live_chat_api)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from services.live_chat_sse_broadcaster import live_chat_sse_broadcaster

_log = logging.getLogger("modules.live_chat_api")


def _log_sse(action: str, **kwargs: Any) -> None:
    """Instrumentation for SSE operations."""
    parts = [f"SSE {action}"]
    for k, v in kwargs.items():
        if v is not None:
            parts.append(f"{k}={v}")
    _log.info(" | ".join(parts))


async def broadcast_sse_event(event_type: str, data: dict) -> None:
    """Fan out to this node and Redis. Never skip Redis because this process has no local clients."""
    import uuid

    from services.live_chat_contracts import utc_now

    payload = dict(data or {})
    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("event_ts", utc_now().isoformat())
    if not str(payload.get("tenant_id") or "").strip() and payload.get("user_id"):
        from services.live_chat_channel import live_chat_event_tenant_id

        payload["tenant_id"] = live_chat_event_tenant_id(payload.get("user_id"))
    if not payload.get("channel") and payload.get("user_id"):
        from services.live_chat_channel import resolve_live_chat_channel

        payload["channel"] = resolve_live_chat_channel(payload.get("user_id"), payload)
    client_count = await live_chat_sse_broadcaster.active_clients_count()
    _log_sse("broadcast", event_type=event_type, client_count=client_count, conv_id=payload.get("conversation_id"))
    if event_type == "new_message":
        print(
            f"📡 [SSE] broadcast new_message conv_id={payload.get('conversation_id')} user_id={payload.get('user_id')}"
        )
    await live_chat_sse_broadcaster.publish(event_type, payload)


def session_allows_live_chat_sse_event(session: Any, event: dict[str, Any] | None) -> bool:
    """Tenant + channel ACL for operator SSE. Missing tenant is dropped (fail closed)."""
    rec = event if isinstance(event, dict) else {}
    event_type = str(rec.get("type") or "")
    if event_type in {"heartbeat", "connected"}:
        return True
    raw_data = rec.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    tenant = str(data.get("tenant_id") or "").strip().lower()
    session_tenant = str(getattr(session, "tenant_id", "") or "").strip().lower()
    if not tenant or not session_tenant or tenant != session_tenant:
        return False
    user_id = str(data.get("user_id") or "")
    if not user_id:
        return event_type == "conversations"
    from services.access_channels import session_can_use_channel
    from services.live_chat_channel import resolve_live_chat_channel

    return session_can_use_channel(session, resolve_live_chat_channel(user_id, data))


def require_chat_channel(http_request: Any, user_id: str) -> Any:
    from modules.api_security import require_session
    from services.access_channels import require_session_channel

    session = require_session(http_request)
    require_session_channel(session, user_id)
    return session


def resolve_takeover_assignee(session: Any, requested_operator_id: str | None) -> tuple[str, str | None]:
    """Session is the actor; requested_operator_id may assign another same-tenant staff member."""
    from fastapi import HTTPException

    from services.takeover_customer_notice import public_staff_label
    from services.user_service import user_service

    session_id = str(getattr(session, "user_id", "") or "").strip()
    requested = str(requested_operator_id or "").strip()
    session_label = public_staff_label(getattr(session, "email", None)) or None
    if not requested or requested == session_id:
        return session_id, session_label

    user = user_service.get_user_by_id(requested)
    if not user:
        raise HTTPException(status_code=400, detail="Staff member not found")
    tenant = str(user.get("tenantId") or "").strip()
    if tenant != str(getattr(session, "tenant_id", "") or "").strip():
        raise HTTPException(status_code=403, detail="Cannot assign to a user in another workspace")
    name = public_staff_label(user.get("name"), user.get("displayName"), user.get("email"))
    return requested, name or session_label


def _error_response(message: str) -> Any:
    return {"success": False, "error": str(message)}


async def _run_endpoint(fn: Callable[[], Awaitable[Any]], fallback: Any | None = None) -> Any:
    from fastapi import HTTPException

    try:
        return await fn()
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive catch-all for API stability
        print(f"❌ Endpoint error: {e}")
        import traceback

        traceback.print_exc()
        return fallback if fallback is not None else _error_response(str(e))
