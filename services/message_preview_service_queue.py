"""Preview-queue CRUD for MessagePreviewService (LOC split)."""

from __future__ import annotations

import uuid
from datetime import datetime


class MessagePreviewQueueMixin:
    """Add/get/approve/reject/edit/batch operations on the preview queue."""

    def add_to_preview_queue(self, message_data: dict) -> dict:
        """
        Add message to preview queue with status 'pending_approval'

        Args:
            message_data: Dict containing:
                - customer_phone: str
                - customer_name: str
                - template_id: str
                - language: str
                - placeholders: Dict
                - service_id: int (optional)
                - service_name: str (optional)
                - scheduled_send_time: datetime/str

        Returns:
            Dict with success status and message_id
        """
        # Create a deduplication key based on customer + template + scheduled time
        customer_phone = message_data.get("customer_phone", "")
        template_id = message_data.get("template_id", "")
        scheduled_time = str(message_data.get("scheduled_send_time", ""))
        dedup_key = f"{customer_phone}_{template_id}_{scheduled_time}"

        # Check if this message already exists in the queue
        for existing_msg in self.preview_queue:
            existing_key = f"{existing_msg.get('customer_phone', '')}_{existing_msg.get('template_id', '')}_{existing_msg.get('scheduled_send_time', '')}"
            if existing_key == dedup_key:
                # Message already exists, skip adding
                return {
                    "success": True,
                    "message_id": existing_msg.get("message_id"),
                    "duplicate": True,
                    "validation_result": existing_msg.get("validation_result"),
                }

        # Generate unique message ID
        message_id = str(uuid.uuid4())[:8] + "_" + datetime.now().strftime("%Y%m%d%H%M%S")

        # Render message content
        rendered_content = self.render_message_preview(
            template_id=str(message_data.get("template_id") or ""),
            language=message_data.get("language", "ar"),
            placeholders=message_data.get("placeholders", {}),
        )

        # Validate message
        validation_result = self.validate_message({**message_data, "rendered_content": rendered_content})

        # Create queue entry
        queue_entry = {
            "message_id": message_id,
            "customer_phone": message_data.get("customer_phone"),
            "customer_name": message_data.get("customer_name", "Unknown"),
            "template_id": message_data.get("template_id"),
            "language": message_data.get("language", "ar"),
            "placeholders": message_data.get("placeholders", {}),
            "service_id": message_data.get("service_id"),
            "service_name": message_data.get("service_name", "Unknown Service"),
            "scheduled_send_time": str(message_data.get("scheduled_send_time", datetime.now())),
            "rendered_content": rendered_content,
            "status": "pending_approval",
            "validation_result": validation_result,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        self.preview_queue.append(queue_entry)
        self._save_preview_queue()

        return {"success": True, "message_id": message_id, "validation_result": validation_result}

    def get_pending_messages(self, status: str | None = "pending_approval", filters: dict | None = None) -> list[dict]:
        """
        Get all messages pending approval

        Args:
            status: Filter by status (pending_approval, approved, rejected, sent, would_send)
            filters: Additional filters (service_id, template_id, date_range)

        Returns:
            List of message dicts
        """
        # Reload from file to get latest
        self.preview_queue = self._load_preview_queue()

        results = []
        for msg in self.preview_queue:
            # Filter by status
            if status and msg.get("status") != status:
                continue

            # Apply additional filters
            if filters:
                if filters.get("service_id") and msg.get("service_id") != filters.get("service_id"):
                    continue
                if filters.get("template_id") and msg.get("template_id") != filters.get("template_id"):
                    continue

            results.append(msg)

        # Sort by scheduled_send_time (earliest first)
        results.sort(key=lambda x: x.get("scheduled_send_time", ""))

        return results

    def get_message_by_id(self, message_id: str) -> dict | None:
        """Get a specific message by ID"""
        for msg in self.preview_queue:
            if msg.get("message_id") == message_id:
                return msg
        return None

    def approve_message(self, message_id: str) -> dict:
        """
        Approve a message for sending

        Args:
            message_id: The message ID to approve

        Returns:
            Dict with success status and message data
        """
        for i, msg in enumerate(self.preview_queue):
            if msg.get("message_id") == message_id:
                self.preview_queue[i]["status"] = "approved"
                self.preview_queue[i]["approved_at"] = datetime.now().isoformat()
                self.preview_queue[i]["updated_at"] = datetime.now().isoformat()
                self._save_preview_queue()

                print(f"Message {message_id} approved for sending")
                return {"success": True, "message": self.preview_queue[i]}

        return {"success": False, "error": f"Message {message_id} not found"}

    def reject_message(self, message_id: str, reason: str | None = None) -> dict:
        """
        Reject and remove a message from the queue

        Args:
            message_id: The message ID to reject
            reason:  reason for rejection

        Returns:
            Dict with success status
        """
        for i, msg in enumerate(self.preview_queue):
            if msg.get("message_id") == message_id:
                self.preview_queue[i]["status"] = "rejected"
                self.preview_queue[i]["rejected_at"] = datetime.now().isoformat()
                self.preview_queue[i]["rejection_reason"] = reason
                self.preview_queue[i]["updated_at"] = datetime.now().isoformat()
                self._save_preview_queue()

                print(f"Message {message_id} rejected: {reason}")
                return {"success": True, "message_id": message_id}

        return {"success": False, "error": f"Message {message_id} not found"}

    def edit_message(self, message_id: str, new_content: dict) -> dict:
        """
        Edit message content before approval

        Args:
            message_id: The message ID to edit
            new_content: Dict with updated fields (rendered_content, placeholders, etc.)

        Returns:
            Dict with success status and updated message
        """
        for i, msg in enumerate(self.preview_queue):
            if msg.get("message_id") == message_id:
                # Update allowed fields
                if "rendered_content" in new_content:
                    self.preview_queue[i]["rendered_content"] = new_content["rendered_content"]
                if "placeholders" in new_content:
                    self.preview_queue[i]["placeholders"] = new_content["placeholders"]
                if "language" in new_content:
                    self.preview_queue[i]["language"] = new_content["language"]
                if "scheduled_send_time" in new_content:
                    self.preview_queue[i]["scheduled_send_time"] = str(new_content["scheduled_send_time"])

                # Re-validate after edit
                self.preview_queue[i]["validation_result"] = self.validate_message(self.preview_queue[i])
                self.preview_queue[i]["updated_at"] = datetime.now().isoformat()
                self.preview_queue[i]["edited"] = True

                self._save_preview_queue()

                print(f"Message {message_id} edited")
                return {"success": True, "message": self.preview_queue[i]}

        return {"success": False, "error": f"Message {message_id} not found"}

    def batch_approve(self, message_ids: list[str]) -> dict:
        """Approve multiple messages at once"""
        approved = []
        failed = []

        for message_id in message_ids:
            result = self.approve_message(message_id)
            if result.get("success"):
                approved.append(message_id)
            else:
                failed.append({"id": message_id, "error": result.get("error")})

        return {
            "success": len(failed) == 0,
            "approved": approved,
            "failed": failed,
            "total_approved": len(approved),
            "total_failed": len(failed),
        }

    def batch_reject(self, message_ids: list[str], reason: str | None = None) -> dict:
        """Reject multiple messages at once"""
        rejected = []
        failed = []

        for message_id in message_ids:
            result = self.reject_message(message_id, reason)
            if result.get("success"):
                rejected.append(message_id)
            else:
                failed.append({"id": message_id, "error": result.get("error")})

        return {
            "success": len(failed) == 0,
            "rejected": rejected,
            "failed": failed,
            "total_rejected": len(rejected),
            "total_failed": len(failed),
        }
