"""Smart messaging preview-queue routes (LOC split)."""

from __future__ import annotations

from typing import Any

from modules.core import app


# ==========================================
# PREVIEW QUEUE ENDPOINTS
# ==========================================


@app.get("/api/smart-messaging/preview-queue/{message_id}")
async def get_preview_message_details(message_id: str) -> Any:
    """Get full details of a single message from the preview queue"""
    try:
        from services.message_preview_service import message_preview_service

        # Get all messages and find the one we need
        all_messages = message_preview_service.get_pending_messages(status="pending_approval")

        for msg in all_messages:
            if msg.get("message_id") == message_id:
                return {"success": True, "message": msg}

        return {"success": False, "error": "Message not found"}
    except Exception as e:
        print(f"Error getting message details: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/preview-queue")
async def get_preview_queue(status: str | None = "pending_approval") -> Any:
    """
    Get messages pending approval with full details.

    Args:
        status: Filter by status (pending_approval, approved, rejected, sent, all)

    Returns messages with:
    - customer_name, customer_phone
    - template_id, service_type
    - rendered message content
    - scheduled_send_time
    - validation_status (errors if any)
    """
    try:
        from services.message_preview_service import message_preview_service

        if status == "all":
            status = None

        messages = message_preview_service.get_pending_messages(status=status)
        stats = message_preview_service.get_queue_stats()

        return {
            "success": True,
            "status_filter": status or "all",
            "total": len(messages),
            "statistics": stats,
            "messages": messages,
        }
    except Exception as e:
        print(f"Error getting preview queue: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/{message_id}/approve")
async def approve_preview_message(message_id: str) -> Any:
    """Approve a single message for sending"""
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.approve_message(message_id)
        return result
    except Exception as e:
        print(f"Error approving message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/{message_id}/reject")
async def reject_preview_message(message_id: str, request_data: dict[str, Any] | None = None) -> Any:
    """Reject/delete a message from the queue"""
    try:
        from services.message_preview_service import message_preview_service

        reason = request_data.get("reason") if request_data else None
        result = message_preview_service.reject_message(message_id, reason)
        return result
    except Exception as e:
        print(f"Error rejecting message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/{message_id}/edit")
async def edit_preview_message(message_id: str, request_data: dict[str, Any]) -> Any:
    """Edit message content before sending"""
    try:
        from services.message_preview_service import message_preview_service
        from services.smart_messaging import smart_messaging

        # First try to edit in preview queue
        result = message_preview_service.edit_message(message_id, request_data)

        if result.get("success"):
            return result

        # If not found in preview queue, try to edit in smart_messaging scheduled messages
        if message_id in smart_messaging.scheduled_messages:
            msg = smart_messaging.scheduled_messages[message_id]

            # Update the message content if provided
            if "rendered_content" in request_data:
                msg["content"] = request_data["rendered_content"]

            # Update scheduled send time if provided
            if "scheduled_send_time" in request_data:
                from datetime import datetime

                try:
                    new_time = datetime.fromisoformat(request_data["scheduled_send_time"].replace("Z", "+00:00"))
                    msg["send_at"] = new_time
                except Exception:
                    pass

            smart_messaging.scheduled_messages[message_id] = msg
            return {"success": True, "message": "Scheduled message updated successfully", "message_id": message_id}

        return {"success": False, "error": "Message not found in any queue"}
    except Exception as e:
        print(f"Error editing message: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/batch-approve")
async def batch_approve_messages(request_data: dict[str, Any]) -> Any:
    """Approve multiple messages at once"""
    try:
        from services.message_preview_service import message_preview_service

        message_ids = request_data.get("message_ids", [])
        if not message_ids:
            return {"success": False, "error": "No message IDs provided"}

        result = message_preview_service.batch_approve(message_ids)
        return result
    except Exception as e:
        print(f"Error batch approving messages: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/batch-reject")
async def batch_reject_messages(request_data: dict[str, Any]) -> Any:
    """Reject multiple messages at once"""
    try:
        from services.message_preview_service import message_preview_service

        message_ids = request_data.get("message_ids", [])
        reason = request_data.get("reason")

        if not message_ids:
            return {"success": False, "error": "No message IDs provided"}

        result = message_preview_service.batch_reject(message_ids, reason)
        return result
    except Exception as e:
        print(f"Error batch rejecting messages: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/validate")
async def validate_message(request_data: dict[str, Any]) -> Any:
    """
    Validate a message before queueing.
    Checks phone format, required variables, and message length.
    """
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.validate_message(request_data)
        return {"success": True, "validation": result}
    except Exception as e:
        print(f"Error validating message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/smart-messaging/preview-queue/add")
async def add_to_preview_queue(request_data: dict[str, Any]) -> Any:
    """
    Add a message to the preview queue.
    Used for testing or manual message addition.
    """
    try:
        from services.message_preview_service import message_preview_service

        result = message_preview_service.add_to_preview_queue(request_data)
        return result
    except Exception as e:
        print(f"Error adding to preview queue: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/smart-messaging/preview-queue/stats")
async def get_preview_queue_stats() -> Any:
    """Get statistics about the preview queue"""
    try:
        from services.message_preview_service import message_preview_service

        stats = message_preview_service.get_queue_stats()
        return {"success": True, "statistics": stats}
    except Exception as e:
        print(f"Error getting queue stats: {e}")
        return {"success": False, "error": str(e)}
