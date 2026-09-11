"""
Live Chat API module: Live chat management endpoints
Handles conversation takeover, operator management, and inbox polling.

Helpers: live_chat_api_helpers (LOC split).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Query, Request

from modules.core import app
from modules.live_chat_api_helpers import (  # noqa: F401
    _run_endpoint,
    broadcast_sse_event,
    require_chat_channel,
    resolve_takeover_assignee,
)
from modules.models import (
    MarkConversationReadRequest,
    OperatorStatusRequest,
    ReleaseRequest,
    SendOperatorMessageRequest,
    TakeoverRequest,
)
from services.live_chat_service import live_chat_service
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

_log = logging.getLogger(__name__)


@app.get("/api/live-chat/unified-chats")
async def get_unified_chats(
    http_request: Request,
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
        from modules.api_security import require_session
        from services.access_channels import effective_inbox_channel, filter_chats_for_session

        session = require_session(http_request)
        inbox_channel = effective_inbox_channel(session, channel)
        if inbox_channel is None:
            return {"success": True, "chats": [], "total": 0, "has_more": False}
        result = await live_chat_service.get_unified_chats(
            search=search,
            page=effective_page,
            page_size=page_size,
            filter_state=filter,
            cursor=None if (cursor and cursor.isdigit()) else cursor,
            channel=inbox_channel,
        )
        if not isinstance(result, dict):
            return result
        return filter_chats_for_session(session, result)

    fallback = {"success": False, "chats": [], "total": 0, "has_more": False, "error": "request_failed"}
    return await _run_endpoint(_handler, fallback=fallback)


@app.post("/api/live-chat/takeover")
async def takeover_conversation(request: TakeoverRequest, http_request: Request) -> Any:
    """Operator takes over a conversation"""

    async def _handler() -> Any:
        session = require_chat_channel(http_request, request.user_id)
        operator_id, operator_name = resolve_takeover_assignee(session, request.operator_id)
        from services.membership.edit_http import guarded_edit

        with guarded_edit(
            tenant_id=str(getattr(session, "tenant_id", "") or ""),
            kind="safety:handoff",
            payload={"action": "takeover", "conversation_id": request.conversation_id},
            safety=True,
        ):
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
        session = require_chat_channel(http_request, request.user_id)
        # Same server-authoritative clear as /resume-ai so WA Cloud epoch cannot stay HUMAN_PAUSED.
        from services.membership.edit_http import guarded_edit

        with guarded_edit(
            tenant_id=str(getattr(session, "tenant_id", "") or ""),
            kind="safety:handoff",
            payload={"action": "release", "conversation_id": request.conversation_id},
            safety=True,
        ):
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


@app.post("/api/live-chat/mark-read")
async def mark_conversation_read(request: MarkConversationReadRequest, http_request: Request) -> Any:
    """Mark conversation as read when operator opens it. Persists unread_count=0 in Firestore."""

    async def _handler() -> Any:
        require_chat_channel(http_request, request.user_id)
        return await live_chat_service.mark_conversation_read(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/send-message")
async def send_operator_message(request: SendOperatorMessageRequest, http_request: Request) -> Any:
    """Send message from operator to customer"""

    async def _handler() -> Any:
        session = require_chat_channel(http_request, request.user_id)
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


@app.get("/api/live-chat/conversation/{user_id}/{conversation_id}")
async def get_conversation_details(
    user_id: str,
    conversation_id: str,
    http_request: Request,
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
        require_chat_channel(http_request, user_id)
        return await live_chat_service.get_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            days=days,
            before=before,
            day_window=day_window,
            max_messages=limit,
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/end-conversation")
async def end_conversation(request: dict, http_request: Request) -> Any:
    """Mark conversation as resolved/ended"""
    conversation_id = request.get("conversation_id")
    user_id = request.get("user_id")

    if not all([conversation_id, user_id]):
        return {
            "success": False,
            "error": "Missing required fields: conversation_id, user_id",
        }
    session = require_chat_channel(http_request, str(user_id))

    async def _handler() -> Any:
        # Clear server pause (Firestore + WA Cloud epoch) before resolving so AI is not stuck paused.
        from services.membership.edit_http import guarded_edit

        with guarded_edit(
            tenant_id=str(getattr(session, "tenant_id", "") or ""),
            kind="safety:handoff",
            payload={"action": "end", "conversation_id": conversation_id},
            safety=True,
        ):
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
