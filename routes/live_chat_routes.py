# -*- coding: utf-8 -*-
"""
Live Chat API Routes - Hybrid Approach
- Groups conversations by client (one card per client)
- 6-hour time filter
- Status management (active/resolved/archived)
- Auto-reopen on new message
"""
from fastapi import APIRouter
from pydantic import BaseModel
from services.live_chat_service import live_chat_service
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

router = APIRouter()

# Pydantic models for Live Chat requests
class TakeoverRequest(BaseModel):
    conversation_id: str
    user_id: str
    operator_id: str
    operator_name: str = None  # Optional operator name for display to customer

class ReleaseRequest(BaseModel):
    conversation_id: str
    user_id: str

class SendOperatorMessageRequest(BaseModel):
    conversation_id: str
    user_id: str
    message: str
    operator_id: str
    message_type: str = "text"  # "text", "voice", "image"

class OperatorStatusRequest(BaseModel):
    operator_id: str
    status: str

class EndConversationRequest(BaseModel):
    conversation_id: str
    user_id: str
    operator_id: str

@router.get("/api/live-chat/active-conversations")
async def get_active_conversations():
    """Get all active conversations (grouped by client, 6-hour filter)"""
    try:
        conversations = await live_chat_service.get_active_conversations()
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        print(f"❌ Error in get_active_conversations: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/api/live-chat/waiting-queue")
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

@router.post("/api/live-chat/takeover")
async def takeover_conversation(request: TakeoverRequest):
    """Operator takes over a conversation"""
    try:
        result = await live_chat_service.takeover_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=request.operator_id,
            operator_name=request.operator_name
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

@router.post("/api/live-chat/release")
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

@router.post("/api/live-chat/send-message")
async def send_operator_message(request: SendOperatorMessageRequest):
    """Send message from operator to customer"""
    try:
        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        result = await live_chat_service.send_operator_message(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            message=request.message,
            operator_id=request.operator_id,
            adapter=adapter,
            message_type=request.message_type  # NOW PASSING MESSAGE_TYPE
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

@router.post("/api/live-chat/end-conversation")
async def end_conversation(request: EndConversationRequest):
    """Mark conversation as resolved/ended"""
    try:
        result = await live_chat_service.end_conversation(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            operator_id=request.operator_id
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

@router.post("/api/live-chat/operator-status")
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

@router.get("/api/live-chat/metrics")
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

@router.get("/api/live-chat/conversation/{user_id}/{conversation_id}")
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

@router.get("/api/live-chat/client/{user_id}/conversations")
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
