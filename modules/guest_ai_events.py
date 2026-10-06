"""SSE for one guest thread. The token only unlocks that guest session."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from modules.core import app
from services.guest.guest_inbox_bridge import guest_live_key, live_token_matches
from services.live_chat.sse_broadcaster import live_chat_sse_broadcaster

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _allows(session_id: str, event: dict[str, Any] | None) -> bool:
    rec: dict[str, Any] = event if isinstance(event, dict) else {}
    if str(rec.get("type") or "") in {"heartbeat", "connected"}:
        return True
    raw = rec.get("data")
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}
    parts = str(data.get("conversation_id") or "").split(":")
    return len(parts) >= 3 and parts[0] == "web" and parts[-1] == session_id


@app.get("/api/guest-ai/events")
async def guest_live_events(
    request: Request,
    guest_session_id: str = Query(min_length=8, max_length=80),
    token: str = Query(min_length=16, max_length=128),
) -> StreamingResponse:
    session_id = guest_session_id.strip()
    if not live_token_matches(session_id, token, key=guest_live_key()):
        raise HTTPException(status_code=401, detail="Guest live token is invalid")
    return StreamingResponse(
        live_chat_sse_broadcaster.stream(request, allow_event=lambda event: _allows(session_id, event)),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
