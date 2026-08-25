"""
Live Chat API module: Live chat management endpoints
Handles conversation takeover, operator management, and real-time communication.
Includes SSE (Server-Sent Events) for real-time dashboard updates.

Helpers/SSE: live_chat_api_helpers; status/debug: live_chat_api_debug (LOC split).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Query, Request
from fastapi.responses import StreamingResponse

# Register status/debug/rebuild routes.
from modules import live_chat_api_debug  # noqa: E402, F401
from modules.core import app, cors_allow_origins
from modules.live_chat_api_helpers import (  # noqa: F401
    _error_response,
    _log_sse,
    _run_endpoint,
    broadcast_sse_event,
    resolve_takeover_assignee,
)
from modules.models import (
    EditMessageRequest,
    MarkConversationReadRequest,
    OperatorStatusRequest,
    ReleaseRequest,
    ResumeAiRequest,
    SendOperatorMessageRequest,
    TakeoverRequest,
)
from services.live_chat_service import live_chat_service
from services.live_chat_sse_broadcaster import live_chat_sse_broadcaster
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

_log = logging.getLogger(__name__)


def _sse_response_headers(request: Request) -> dict[str, str]:
    """SSE headers: reflect Origin only when it matches app CORS allowlist (never *)."""
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Vary": "Origin",
    }
    origin = (request.headers.get("origin") or "").strip()
    if origin and origin in cors_allow_origins():
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


# ============================================================
# SSE (Server-Sent Events) for Real-Time Updates
# ============================================================
# No initial payload - frontend fetches via direct API for faster load.
# SSE used only for real-time: new_message, new_conversation, heartbeat.


@app.get("/api/live-chat/events")
async def live_chat_events(request: Request) -> Any:
    """
    SSE endpoint for real-time live chat updates.
    Dashboard connects here instead of polling.

    Events:
    - connected: Initial connection established
    - conversations: Full conversation list update
    - new_message: New message in a conversation
    - new_conversation: New conversation created
    - heartbeat: Keep-alive ping every 30s
    """
    _log_sse("client_connect")
    return StreamingResponse(
        live_chat_sse_broadcaster.stream(request),
        media_type="text/event-stream",
        headers=_sse_response_headers(request),
    )


@app.get("/api/live-chat/unified-chats")
async def get_unified_chats(
    search: str = Query(default="", description="Search by name or phone"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    cursor: str = Query(default=None, description="Cursor string returned by previous page"),
    filter: str = Query(default="all", description="Badge filter: all|waiting|with_operator|bot|closed"),
    channel: str = Query(default="all", description="Channel: all|whatsapp|instagram|facebook|tiktok|web"),
) -> Any:
    """WhatsApp-style inbox (single master list) powered by live_chat_index."""
    _log.info(
        "live_chat_api.get_unified_chats search=%s page=%s page_size=%s filter=%s channel=%s cursor=%s",
        bool(search and search.strip()),
        page,
        page_size,
        filter,
        channel,
        bool(cursor),
    )
    effective_page = int(cursor) if (cursor and cursor.isdigit()) else page

    async def _handler() -> Any:
        return await live_chat_service.get_unified_chats(
            search=search,
            page=effective_page,
            page_size=page_size,
            filter_state=filter,
            cursor=None if (cursor and cursor.isdigit()) else cursor,
            channel=channel,
        )

    fallback = {"success": False, "chats": [], "total": 0, "has_more": False, "error": "request_failed"}
    return await _run_endpoint(_handler, fallback=fallback)


@app.get("/api/live-chat/chats-by-template-send-log")
async def get_chats_by_template_send_log(
    template_id: str = Query(..., description="Smart Messaging template id"),
    date_from: str = Query(default="", description="Optional YYYY-MM-DD (UTC) start of sent_at range"),
    date_to: str = Query(default="", description="Optional YYYY-MM-DD (UTC) end of sent_at range"),
    scan_limit: int = Query(default=0, ge=0, le=20000),
) -> Any:
    """
    List live_chat_index conversations for customers who have a message_logs row
    for this template (successful sends). Scans newest index rows first (see scan_limit / env).
    """

    async def _handler() -> Any:
        lim = int(scan_limit) if scan_limit else None
        return await live_chat_service.get_chats_by_template_send_log(
            template_id=template_id,
            date_from=date_from.strip() or None,
            date_to=date_to.strip() or None,
            scan_limit=lim,
        )

    return await _run_endpoint(_handler, fallback={"success": False, "chats": [], "error": "request_failed"})


@app.get("/api/live-chat/active-conversations")
async def get_active_conversations(
    search: str = Query(default="", description="Search by client name or phone"),
) -> Any:
    """Get active conversations with optional client search."""

    async def _handler() -> Any:
        unified = await live_chat_service.get_unified_chats(
            search=search or "",
            page=1,
            page_size=200,
        )
        if not unified.get("success"):
            return {
                "success": False,
                "conversations": [],
                "total": 0,
                "search": search,
                "source": unified.get("source"),
                "error": unified.get("error") or "live_chat_unavailable",
            }

        conversations = [
            {
                "conversation_id": c.get("conversation_id"),
                "user_id": c.get("user_id"),
                "user_name": c.get("user_name"),
                "user_phone": c.get("user_phone") or c.get("phone_number"),
                "phone_clean": c.get("phone_clean"),
                "last_message": c.get("last_message_text")
                or ((c.get("last_message") or {}).get("content") if isinstance(c.get("last_message"), dict) else ""),
                "last_activity": c.get("last_activity") or c.get("last_message_at"),
                "status": c.get("status") or "bot",
                "conversation_state": c.get("conversation_state"),
                "operator_id": c.get("operator_id"),
                "unread_count": c.get("unread_count", 0),
                "is_new_customer": c.get("is_new_customer", False),
            }
            for c in unified.get("chats", [])
        ]
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations),
            "search": search,
            "source": unified.get("source"),
        }

    return await _run_endpoint(_handler)


@app.get("/api/live-chat/waiting-queue")
async def get_waiting_queue() -> Any:
    """Get conversations waiting for human intervention"""
    _log.info("live_chat_api.get_waiting_queue")

    async def _handler() -> Any:
        queue = await live_chat_service.get_waiting_queue()
        return {
            "success": True,
            "queue": queue,
            "total": len(queue),
        }

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/takeover")
async def takeover_conversation(request: TakeoverRequest, http_request: Request) -> Any:
    """Operator takes over a conversation"""

    async def _handler() -> Any:
        from modules.api_security import require_session

        session = require_session(http_request)
        operator_id, operator_name = resolve_takeover_assignee(session, request.operator_id)
        result = await live_chat_service.takeover_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=operator_id,
            operator_name=operator_name,
            tenant_id=getattr(session, "tenant_id", None),
        )
        if result.get("success"):
            # Broadcast so all clients (including other tabs) refresh and move conv from Waiting to Active
            await broadcast_sse_event("conversations", {"trigger_refresh": True})
        return result

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/release")
async def release_conversation(request: ReleaseRequest, http_request: Request) -> Any:
    """Release conversation back to bot (explicit Resume AI — clears server pause)."""

    async def _handler() -> Any:
        from modules.api_security import require_session

        session = require_session(http_request)
        # Same server-authoritative clear as /resume-ai so WA Cloud epoch cannot stay HUMAN_PAUSED.
        result = await live_chat_service.resume_ai_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=session.user_id,
            tenant_id=getattr(session, "tenant_id", None),
        )
        if result.get("success"):
            await broadcast_sse_event("conversations", {"trigger_refresh": True})
        return result

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/resume-ai")
async def resume_ai_conversation(request: ResumeAiRequest, http_request: Request) -> Any:
    """Explicit Resume AI — clears server-authoritative manual pause."""

    async def _handler() -> Any:
        from modules.api_security import require_session

        session = require_session(http_request)
        result = await live_chat_service.resume_ai_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=session.user_id,
            tenant_id=getattr(session, "tenant_id", None),
            request_id=request.request_id,
            source_channel=request.source_channel,
        )
        if result.get("success"):
            await broadcast_sse_event("conversations", {"trigger_refresh": True})
        return result

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/mark-read")
async def mark_conversation_read(request: MarkConversationReadRequest, http_request: Request) -> Any:
    """Mark conversation as read when operator opens it. Persists unread_count=0 in Firestore."""

    async def _handler() -> Any:
        from modules.api_security import require_session

        require_session(http_request)
        return await live_chat_service.mark_conversation_read(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/send-message")
async def send_operator_message(request: SendOperatorMessageRequest, http_request: Request) -> Any:
    """Send message from operator to customer"""

    async def _handler() -> Any:
        from modules.api_security import require_session

        session = require_session(http_request)
        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        return await live_chat_service.send_operator_message(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            message=request.message,
            operator_id=session.user_id,
            message_type=request.message_type,
            adapter=adapter,
            idempotency_key=request.idempotency_key,
            tenant_id=getattr(session, "tenant_id", None),
            operator_name=getattr(session, "email", None),
            request_id=getattr(request, "request_id", None),
            source_channel=getattr(request, "source_channel", None),
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/operator-status")
async def update_operator_status(request: OperatorStatusRequest, http_request: Request) -> Any:
    """Update operator availability status (actor from session — body operator_id ignored)."""

    async def _handler() -> Any:
        from modules.api_security import require_session

        session = require_session(http_request)
        return await live_chat_service.update_operator_status(
            operator_id=session.user_id,
            status=request.status,
        )

    return await _run_endpoint(_handler)


@app.get("/api/live-chat/metrics")
async def get_live_chat_metrics() -> Any:
    """Get real-time live chat metrics"""

    async def _handler() -> Any:
        return await live_chat_service.get_metrics()

    return await _run_endpoint(_handler)


@app.get("/api/live-chat/faq-match-context")
async def get_faq_match_context(
    user_id: str = Query(..., description="User ID"),
    conversation_id: str = Query(..., description="Conversation ID"),
    message_id: str = Query(..., description="Message ID"),
) -> Any:
    """Get FAQ match metadata and current FAQ entry for a message (for FAQ correction modal)."""

    async def _handler() -> Any:
        return await live_chat_service.get_faq_match_context(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )

    return await _run_endpoint(_handler)


@app.get("/api/live-chat/conversation/{user_id}/{conversation_id}")
async def get_conversation_details(
    user_id: str,
    conversation_id: str,
    days: int = Query(default=0, description="Return only last N days (0=all)"),
    before: str = Query(default=None, description="Load messages older than this ISO timestamp (Load More)"),
    day_window: int = Query(
        default=0, description="With before: return only messages from this many days back (1 = one more day)"
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Max messages per request (50 default, up to 100)"),
) -> Any:
    """Get detailed conversation history. Initial: last 1 day. Load More: before=oldest_ts, day_window=1 for one more day."""
    _log.info(
        "live_chat_api.get_conversation_details days=%s before=%s day_window=%s limit=%s",
        days,
        bool(before),
        day_window,
        limit,
    )

    async def _handler() -> Any:
        return await live_chat_service.get_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            days=days,
            before=before,
            day_window=day_window,
            max_messages=limit,
        )

    return await _run_endpoint(_handler)


@app.get("/api/live-chat/client/{user_id}/conversations")
async def get_client_all_conversations(user_id: str) -> Any:
    """Get all conversations for a specific client (for expanded view)"""

    async def _handler() -> Any:
        conversations = await live_chat_service.get_client_conversations(user_id)
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations),
        }

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/edit-message")
async def edit_message(request: EditMessageRequest, http_request: Request) -> Any:
    """Edit a bot message's content (e.g. after operator dislike). Updates Firestore and broadcasts."""

    async def _handler() -> Any:
        from modules.api_security import require_session

        require_session(http_request)
        return await live_chat_service.update_message_content(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            message_id=request.message_id,
            new_content=request.new_content,
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/end-conversation")
async def end_conversation(request: dict, http_request: Request) -> Any:
    """Mark conversation as resolved/ended"""
    from modules.api_security import require_session

    session = require_session(http_request)
    conversation_id = request.get("conversation_id")
    user_id = request.get("user_id")

    if not all([conversation_id, user_id]):
        return {
            "success": False,
            "error": "Missing required fields: conversation_id, user_id",
        }

    async def _handler() -> Any:
        # Clear server pause (Firestore + WA Cloud epoch) before resolving so AI is not stuck paused.
        resume = await live_chat_service.resume_ai_conversation(
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            operator_id=session.user_id,
            tenant_id=getattr(session, "tenant_id", None),
        )
        if not resume.get("success"):
            print(f"⚠️ end-conversation: resume before end failed: {resume.get('error')}")
        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        return await live_chat_service.end_conversation(
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            operator_id=session.user_id,
            adapter=adapter,
        )

    return await _run_endpoint(_handler)
