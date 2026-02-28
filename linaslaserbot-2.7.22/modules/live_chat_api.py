# -*- coding: utf-8 -*-
"""
Live Chat API module: Live chat management endpoints
Handles conversation takeover, operator management, and real-time communication.
Includes SSE (Server-Sent Events) for real-time dashboard updates.
"""

import asyncio
import json
from datetime import datetime
from fastapi import Request, Query
from fastapi.responses import StreamingResponse


def json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

from modules.core import app
from modules.models import (
    TakeoverRequest,
    ReleaseRequest,
    SendOperatorMessageRequest,
    OperatorStatusRequest
)
from services.live_chat_service import live_chat_service
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

# ============================================================
# SSE (Server-Sent Events) for Real-Time Updates
# ============================================================
# Global set to track connected SSE clients
_sse_clients: set = set()

async def sse_event_generator(request: Request):
    """
    Generator that yields SSE events to connected clients.
    Keeps connection alive and sends updates when available.
    """
    client_queue = asyncio.Queue()
    _sse_clients.add(client_queue)
    print(f"📡 SSE client connected. Active clients: {len(_sse_clients)}")

    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        # Send current conversations immediately
        try:
            conversations = await live_chat_service.get_active_conversations()
            yield f"event: conversations\ndata: {json.dumps({'conversations': conversations, 'total': len(conversations)}, default=json_serializer)}\n\n"
        except Exception as e:
            print(f"⚠️ SSE: Error sending initial conversations: {e}")

        # Keep connection alive and send updates
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for an event with timeout (for heartbeat)
                event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                print(f"📡 SSE: Got event from queue: {event['type']}")
                event_data = json.dumps(event['data'], default=json_serializer)
                print(f"📡 SSE: Yielding event to client: {event['type']}")
                yield f"event: {event['type']}\ndata: {event_data}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                print(f"📡 SSE: Sending heartbeat")
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': asyncio.get_event_loop().time()})}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        _sse_clients.discard(client_queue)
        print(f"📡 SSE client disconnected. Active clients: {len(_sse_clients)}")

async def broadcast_sse_event(event_type: str, data: dict):
    """
    Broadcast an event to all connected SSE clients.
    Called when new messages arrive or conversations change.
    """
    print(f"📡 SSE broadcast called: {event_type}, clients: {len(_sse_clients)}")
    if not _sse_clients:
        print(f"📡 SSE: No clients connected, skipping broadcast")
        return

    event = {"type": event_type, "data": data}
    disconnected = set()

    for client_queue in _sse_clients:
        try:
            client_queue.put_nowait(event)
            print(f"📡 SSE: Event queued successfully for client")
        except Exception as e:
            print(f"📡 SSE: Error queuing event: {e}")
            disconnected.add(client_queue)

    # Clean up disconnected clients
    _sse_clients.difference_update(disconnected)

@app.get("/api/live-chat/events")
async def live_chat_events(request: Request):
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
    return StreamingResponse(
        sse_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.get("/api/live-chat/active-conversations")
async def get_active_conversations(search: str = Query(default="", description="Search by client name or phone")):
    """Get active conversations with optional client search."""
    try:
        conversations = await live_chat_service.get_active_conversations(search=search)
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations),
            "search": search
        }
    except Exception as e:
        print(f"❌ Error in get_active_conversations: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/live-chat/waiting-queue")
async def get_waiting_queue():
    """Get conversations waiting for human intervention"""
    try:
        queue = await live_chat_service.get_waiting_queue()
        return {
            "success": True,
            "queue": queue,
            "total": len(queue)
        }
    except Exception as e:
        print(f"❌ Error in get_waiting_queue: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/live-chat/takeover")
async def takeover_conversation(request: TakeoverRequest):
    """Operator takes over a conversation"""
    try:
        result = await live_chat_service.takeover_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=request.operator_id
        )
        return result
    except Exception as e:
        print(f"❌ Error in takeover_conversation: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/live-chat/release")
async def release_conversation(request: ReleaseRequest):
    """Release conversation back to bot"""
    try:
        result = await live_chat_service.release_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id
        )
        return result
    except Exception as e:
        print(f"❌ Error in release_conversation: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/live-chat/send-message")
async def send_operator_message(request: SendOperatorMessageRequest):
    """Send message from operator to customer"""
    try:
        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        result = await live_chat_service.send_operator_message(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            message=request.message,
            operator_id=request.operator_id,
            message_type=request.message_type,
            adapter=adapter
        )
        return result
    except Exception as e:
        print(f"❌ Error in send_operator_message: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/live-chat/operator-status")
async def update_operator_status(request: OperatorStatusRequest):
    """Update operator availability status"""
    try:
        result = await live_chat_service.update_operator_status(
            operator_id=request.operator_id,
            status=request.status
        )
        return result
    except Exception as e:
        print(f"❌ Error in update_operator_status: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/live-chat/metrics")
async def get_live_chat_metrics():
    """Get real-time live chat metrics"""
    try:
        metrics = await live_chat_service.get_metrics()
        return metrics
    except Exception as e:
        print(f"❌ Error in get_live_chat_metrics: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/live-chat/conversation/{user_id}/{conversation_id}")
async def get_conversation_details(user_id: str, conversation_id: str):
    """Get detailed conversation history"""
    try:
        details = await live_chat_service.get_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id
        )
        return details
    except Exception as e:
        print(f"❌ Error in get_conversation_details: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/live-chat/client/{user_id}/conversations")
async def get_client_all_conversations(user_id: str):
    """Get all conversations for a specific client (for expanded view)"""
    try:
        conversations = await live_chat_service.get_client_conversations(user_id)
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        print(f"❌ Error in get_client_all_conversations: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/live-chat/end-conversation")
async def end_conversation(request: dict):
    """Mark conversation as resolved/ended"""
    try:
        conversation_id = request.get("conversation_id")
        user_id = request.get("user_id")
        operator_id = request.get("operator_id")

        if not all([conversation_id, user_id, operator_id]):
            return {
                "success": False,
                "error": "Missing required fields: conversation_id, user_id, operator_id"
            }

        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())

        result = await live_chat_service.end_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            operator_id=operator_id,
            adapter=adapter
        )
        return result
    except Exception as e:
        print(f"❌ Error in end_conversation: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/live-chat/debug-firestore")
async def debug_firestore():
    """Debug endpoint to check Firestore data without cache"""
    try:
        from utils.utils import get_firestore_db
        import config
        import datetime

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

                last_message_time = None
                hours_ago = None
                if messages:
                    last_msg = messages[-1]
                    timestamp = last_msg.get("timestamp")
                    if timestamp:
                        if isinstance(timestamp, str):
                            try:
                                last_message_time = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            except:
                                pass
                        elif hasattr(timestamp, 'timestamp'):
                            last_message_time = timestamp

                        if last_message_time:
                            try:
                                # Try to calculate hours ago, handle timezone issues
                                now = datetime.datetime.now()
                                # Convert both to naive datetimes to avoid timezone issues
                                if hasattr(last_message_time, 'replace') and hasattr(last_message_time, 'tzinfo'):
                                    if last_message_time.tzinfo:
                                        last_message_time = last_message_time.replace(tzinfo=None)
                                hours_ago = (now - last_message_time).total_seconds() / 3600
                            except Exception as e:
                                print(f"Error calculating hours_ago: {e}")
                                hours_ago = None

                conversations_info.append({
                    "id": conv_doc.id,
                    "message_count": len(messages),
                    "status": status,
                    "hours_ago": round(hours_ago, 1) if hours_ago else None,
                    "human_takeover": conv_data.get("human_takeover_active", False)
                })

            users_data.append({
                "user_id": user_id,
                "conversation_count": len(conversations_docs),
                "conversations": conversations_info
            })

        return {
            "success": True,
            "total_users": len(users_docs),
            "users": users_data
        }
    except Exception as e:
        print(f"❌ Error in debug_firestore: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
