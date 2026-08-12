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
    """
    Broadcast an event to all connected SSE clients.
    Called when new messages arrive or conversations change.
    """
    client_count = await live_chat_sse_broadcaster.active_clients_count()
    if client_count == 0:
        return
    _log_sse("broadcast", event_type=event_type, client_count=client_count, conv_id=data.get("conversation_id"))
    if event_type == "new_message":
        print(f"📡 [SSE] broadcast new_message conv_id={data.get('conversation_id')} user_id={data.get('user_id')}")
    await live_chat_sse_broadcaster.publish(event_type, data)


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
