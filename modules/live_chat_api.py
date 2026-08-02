"""
Live Chat API module: Live chat management endpoints
Handles conversation takeover, operator management, and real-time communication.
Includes SSE (Server-Sent Events) for real-time dashboard updates.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Query, Request
from fastapi.responses import StreamingResponse

from modules.core import app
from modules.models import (
    EditMessageRequest,
    MarkConversationReadRequest,
    OperatorStatusRequest,
    ReleaseRequest,
    SendOperatorMessageRequest,
    TakeoverRequest,
)
from services.live_chat_service import live_chat_service
from services.live_chat_sse_broadcaster import live_chat_sse_broadcaster
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

_log = logging.getLogger(__name__)


def _log_sse(action: str, **kwargs: Any) -> None:
    """Instrumentation for SSE operations."""
    parts = [f"SSE {action}"]
    for k, v in kwargs.items():
        if v is not None:
            parts.append(f"{k}={v}")
    _log.info(" | ".join(parts))


# ============================================================
# SSE (Server-Sent Events) for Real-Time Updates
# ============================================================
# No initial payload - frontend fetches via direct API for faster load.
# SSE used only for real-time: new_message, new_conversation, heartbeat.


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
    print("📡 [SSE] client connected")
    return StreamingResponse(
        live_chat_sse_broadcaster.stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/live-chat/unified-chats")
async def get_unified_chats(
    search: str = Query(default="", description="Search by name or phone"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    cursor: str = Query(default=None, description="Cursor string returned by previous page"),
    filter: str = Query(default="all", description="Badge filter: all|waiting|with_operator|bot|closed"),
) -> Any:
    """WhatsApp-style inbox (single master list) powered by live_chat_index."""
    _log.info(
        "live_chat_api.get_unified_chats search=%s page=%s page_size=%s filter=%s cursor=%s",
        bool(search and search.strip()),
        page,
        page_size,
        filter,
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
        )

    fallback = {"success": False, "chats": [], "total": 0, "has_more": False}
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
        from modules.api_security import reject_social_operator_mutation, require_session

        session = require_session(http_request)
        reject_social_operator_mutation(request.user_id)
        result = await live_chat_service.takeover_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=session.user_id,
            operator_name=session.email,
        )
        if result.get("success"):
            # Broadcast so all clients (including other tabs) refresh and move conv from Waiting to Active
            await broadcast_sse_event("conversations", {"trigger_refresh": True})
        return result

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/release")
async def release_conversation(request: ReleaseRequest, http_request: Request) -> Any:
    """Release conversation back to bot"""

    async def _handler() -> Any:
        from modules.api_security import reject_social_operator_mutation, require_session

        require_session(http_request)
        reject_social_operator_mutation(request.user_id)
        result = await live_chat_service.release_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
        )
        if result.get("success"):
            await broadcast_sse_event("conversations", {"trigger_refresh": True})
        return result

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/mark-read")
async def mark_conversation_read(request: MarkConversationReadRequest) -> Any:
    """Mark conversation as read when operator opens it. Persists unread_count=0 in Firestore."""

    async def _handler() -> Any:
        return await live_chat_service.mark_conversation_read(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/send-message")
async def send_operator_message(request: SendOperatorMessageRequest, http_request: Request) -> Any:
    """Send message from operator to customer"""

    async def _handler() -> Any:
        from modules.api_security import reject_social_operator_mutation, require_session

        session = require_session(http_request)
        reject_social_operator_mutation(request.user_id)
        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        return await live_chat_service.send_operator_message(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            message=request.message,
            operator_id=session.user_id,
            message_type=request.message_type,
            adapter=adapter,
            idempotency_key=request.idempotency_key,
        )

    return await _run_endpoint(_handler)


@app.post("/api/live-chat/operator-status")
async def update_operator_status(request: OperatorStatusRequest) -> Any:
    """Update operator availability status"""

    async def _handler() -> Any:
        return await live_chat_service.update_operator_status(
            operator_id=request.operator_id,
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
        "live_chat_api.get_conversation_details user_id=%s conversation_id=%s days=%s before=%s day_window=%s limit=%s",
        user_id,
        conversation_id,
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

    result = await _run_endpoint(_handler)
    # #region agent log
    try:
        import json
        import os

        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _logpath = os.path.join(_root, ".cursor", "debug-420609.log")
        os.makedirs(os.path.dirname(_logpath), exist_ok=True)
        with open(_logpath, "a") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "420609",
                        "location": "live_chat_api:get_conversation_details",
                        "message": "API response",
                        "data": {
                            "user_id": user_id,
                            "conv_id": conversation_id,
                            "success": result.get("success") if isinstance(result, dict) else False,
                            "msg_count": len(result.get("messages", [])) if isinstance(result, dict) else 0,
                            "error": result.get("error") if isinstance(result, dict) else None,
                        },
                        "timestamp": int(__import__("time").time() * 1000),
                        "hypothesisId": "H1",
                    }
                )
                + "\n"
            )
    except Exception as e:
        print(f"[DEBUG] log write failed: {e}")
    # #endregion
    return result


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
        from modules.api_security import reject_social_operator_mutation, require_session

        require_session(http_request)
        reject_social_operator_mutation(request.user_id)
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
    from modules.api_security import reject_social_operator_mutation, require_session

    session = require_session(http_request)
    conversation_id = request.get("conversation_id")
    user_id = request.get("user_id")

    if not all([conversation_id, user_id]):
        return {
            "success": False,
            "error": "Missing required fields: conversation_id, user_id",
        }

    reject_social_operator_mutation(user_id)

    async def _handler() -> Any:
        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        return await live_chat_service.end_conversation(
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            operator_id=session.user_id,
            adapter=adapter,
        )

    return await _run_endpoint(_handler)


@app.get("/api/live-chat/status")
async def live_chat_status() -> Any:
    """Quick status: index count, users count. If index empty but users exist, call rebuild-index."""
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if not db:
            return {"success": False, "error": "Firestore not available", "index_count": 0, "users_count": 0}
        app_id = "linas-ai-bot-backend"
        idx_coll = db.collection("artifacts").document(app_id).collection("live_chat_index")
        users_coll = db.collection("artifacts").document(app_id).collection("users")
        index_docs = list(idx_coll.limit(1000).stream())
        users_docs = list(users_coll.limit(1000).stream())
        index_count = len(index_docs)
        users_count = len(users_docs)
        suggestion = None
        if users_count > 0 and index_count == 0:
            suggestion = "Call POST /api/live-chat/rebuild-index to populate from Firestore conversations"
        return {
            "success": True,
            "index_count": index_count,
            "users_count": users_count,
            "suggestion": suggestion,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "index_count": 0, "users_count": 0}


@app.get("/api/live-chat/debug-firestore")
async def debug_firestore() -> Any:
    """Debug endpoint to check Firestore data without cache"""
    try:
        import datetime

        import config
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if not db:
            return {"success": False, "error": "Firestore not available"}

        app_id = "linas-ai-bot-backend"
        users_collection = db.collection("artifacts").document(app_id).collection("users")

        users_docs = list(users_collection.stream())
        users_data = []

        for user_doc in users_docs:
            user_id = user_doc.id
            conversations_collection = users_collection.document(user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            )
            conversations_docs = list(conversations_collection.stream())

            conversations_info = []
            for conv_doc in conversations_docs:
                conv_data = conv_doc.to_dict()
                messages = conv_data.get("messages", [])
                status = conv_data.get("status", "active")
                conv_state = conv_data.get("conversation_state")

                last_message_time = None
                hours_ago = None
                if messages:
                    last_msg = messages[-1]
                    timestamp = last_msg.get("timestamp")
                    if timestamp:
                        if isinstance(timestamp, str):
                            try:
                                last_message_time = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            except Exception:
                                pass
                        elif hasattr(timestamp, "timestamp"):
                            last_message_time = timestamp

                        if last_message_time:
                            try:
                                # Try to calculate hours ago, handle timezone issues
                                now = datetime.datetime.now()
                                # Convert both to naive datetimes to avoid timezone issues
                                if hasattr(last_message_time, "replace") and hasattr(last_message_time, "tzinfo"):
                                    if last_message_time.tzinfo:
                                        last_message_time = last_message_time.replace(tzinfo=None)
                                hours_ago = (now - last_message_time).total_seconds() / 3600
                            except Exception as e:
                                print(f"Error calculating hours_ago: {e}")
                                hours_ago = None

                conversations_info.append(
                    {
                        "id": conv_doc.id,
                        "message_count": len(messages),
                        "status": status,
                        "conversation_state": conv_state,
                        "hours_ago": round(hours_ago, 1) if hours_ago else None,
                        "human_takeover": conv_data.get("human_takeover_active", False),
                    }
                )

            # Lookup live_chat_index doc for this user_id for quick parity check
            index_doc = db.collection("artifacts").document(app_id).collection("live_chat_index")
            idx_docs = list(index_doc.where("user_id", "==", user_id).limit(5).stream())
            index_entries = []
            for idx in idx_docs:
                data = idx.to_dict() or {}
                index_entries.append(
                    {
                        "conversation_id": idx.id,
                        "state": data.get("conversation_state"),
                        "last_message_at": str(data.get("last_message_at")),
                        "last_message_text": data.get("last_message_text"),
                        "unread_count": data.get("unread_count", 0),
                    }
                )

            users_data.append(
                {
                    "user_id": user_id,
                    "conversation_count": len(conversations_docs),
                    "conversations": conversations_info,
                    "index_entries": index_entries,
                }
            )

        return {"success": True, "total_users": len(users_docs), "users": users_data}
    except Exception as e:
        print(f"❌ Error in debug_firestore: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/live-chat/rebuild-index")
async def rebuild_live_chat_index(
    max_users: int = Query(default=None), max_conversations_per_user: int = Query(default=None)
) -> Any:
    """Temporary debug endpoint to rebuild/backfill live_chat_index from Firestore conversations."""

    async def _handler() -> Any:
        written = await live_chat_service.rebuild_index_from_firestore(
            max_users=max_users,
            max_conversations_per_user=max_conversations_per_user,
            set_conversation_state=True,
        )
        return {"success": True, "written": written}

    return await _run_endpoint(_handler)
