#!/usr/bin/env python3
"""
Message Preview Service - Manage message preview queue for approval workflow
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, cast

from services.message_preview_service_queue import MessagePreviewQueueMixin
from services.message_preview_service_settings import MessagePreviewSettingsMixin
from storage.persistent_storage import (
    APP_SETTINGS_FILE,
    MESSAGE_PREVIEW_QUEUE_FILE,
    MESSAGE_TEMPLATES_FILE,
    ensure_dirs,
)


class MessagePreviewService(MessagePreviewSettingsMixin, MessagePreviewQueueMixin):
    """
    Service to manage message preview queue for approval before sending
    """

    def __init__(self) -> None:
        ensure_dirs()
        self.preview_queue_file = str(MESSAGE_PREVIEW_QUEUE_FILE)
        self.app_settings_file = str(APP_SETTINGS_FILE)
        self.templates_file = str(MESSAGE_TEMPLATES_FILE)
        self.preview_queue = self._load_preview_queue()
        print(f"MessagePreviewService initialized with {len(self.preview_queue)} pending messages")

    def _load_preview_queue(self) -> list[dict]:
        """Load preview queue from JSON file"""
        if not os.path.exists(self.preview_queue_file):
            return []
        try:
            with open(self.preview_queue_file, encoding="utf-8") as f:
                return cast(list[dict[Any, Any]], json.load(f))
        except Exception as e:
            print(f"Error loading preview queue: {e}")
            return []

    def _save_preview_queue(self) -> bool:
        """Save preview queue to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.preview_queue_file), exist_ok=True)
            with open(self.preview_queue_file, "w", encoding="utf-8") as f:
                json.dump(self.preview_queue, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            print(f"Error saving preview queue: {e}")
            return False

    def validate_message(self, message_data: dict) -> dict:
        """
        Validate message before sending

        Args:
            message_data: Message data including rendered_content, customer_phone, etc.

        Returns:
            Dict with valid status and list of errors
        """
        errors = []
        settings = self.get_settings()
        validation_rules = settings.get("validationRules", {})

        # 1. Phone number validation
        phone = message_data.get("customer_phone", "")
        phone_clean = str(phone).replace("+", "").replace("-", "").replace(" ", "")

        min_phone_len = validation_rules.get("minPhoneLength", 8)
        max_phone_len = validation_rules.get("maxPhoneLength", 15)

        if len(phone_clean) < min_phone_len:
            errors.append(f"Phone number too short (min {min_phone_len} digits)")
        if len(phone_clean) > max_phone_len:
            errors.append(f"Phone number too long (max {max_phone_len} digits)")
        if phone_clean and not phone_clean.isdigit():
            errors.append("Phone number contains invalid characters")

        # Lebanon format check (961 + 8 digits)
        if phone_clean.startswith("961"):
            local_number = phone_clean[3:]
            if len(local_number) != 8:
                errors.append("Lebanese phone should be 961 + 8 digits")

        # 2. Required variables check
        placeholders = message_data.get("placeholders", {})
        required_vars = validation_rules.get("requiredVariables", ["customer_name"])

        for var in required_vars:
            if not placeholders.get(var):
                errors.append(f"Missing required variable: {var}")

        # 3. Check for unfilled placeholders in rendered content
        rendered_content = message_data.get("rendered_content", "")
        if rendered_content:
            unfilled = re.findall(r"\{(\w+)\}", rendered_content)
            if unfilled:
                errors.append(f"Unfilled placeholders: {', '.join(unfilled)}")

        # 4. Message length check (WhatsApp limit)
        max_msg_len = validation_rules.get("maxMessageLength", 1600)
        if len(rendered_content) > max_msg_len:
            errors.append(f"Message too long: {len(rendered_content)} chars (max {max_msg_len})")

        return {"valid": len(errors) == 0, "errors": errors}

    def render_message_preview(self, template_id: str, language: str, placeholders: dict) -> str:
        """
        Render full message with placeholders filled

        Args:
            template_id: Template ID to use
            language: Language code (ar, en, fr)
            placeholders: Dict of placeholder values

        Returns:
            Rendered message string
        """
        templates = self._load_templates()

        if template_id not in templates:
            return f"[Template '{template_id}' not found]"

        template = templates[template_id]
        template_text = template.get(language, template.get("ar", ""))

        if not template_text:
            return f"[Template '{template_id}' has no content for language '{language}']"

        # Replace placeholders
        rendered = template_text
        for key, value in placeholders.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))

        return cast(str, rendered)

    def get_approved_messages(self) -> list[dict]:
        """Get messages that have been approved and are ready to send"""
        return self.get_pending_messages(status="approved")

    def mark_as_sent(self, message_id: str) -> dict:
        """Mark a message as sent after successful delivery"""
        for i, msg in enumerate(self.preview_queue):
            if msg.get("message_id") == message_id:
                self.preview_queue[i]["status"] = "sent"
                self.preview_queue[i]["sent_at"] = datetime.now().isoformat()
                self.preview_queue[i]["updated_at"] = datetime.now().isoformat()
                self._save_preview_queue()
                return {"success": True}

        return {"success": False, "error": f"Message {message_id} not found"}

    def mark_would_send(self, message_id: str) -> dict:
        """
        Mark an approved preview row as would_send (dry-run / no real WhatsApp).
        Stops the scheduler from retrying the same approved row every tick when
        the row is not present in smart_messaging.scheduled_messages (e.g. after restart).
        """
        self.preview_queue = self._load_preview_queue()
        for i, msg in enumerate(self.preview_queue):
            if msg.get("message_id") == message_id:
                self.preview_queue[i]["status"] = "would_send"
                self.preview_queue[i]["would_send_at"] = datetime.now().isoformat()
                self.preview_queue[i]["updated_at"] = datetime.now().isoformat()
                self._save_preview_queue()
                return {"success": True}
        return {"success": False, "error": f"Message {message_id} not found"}

    def get_queue_stats(self) -> dict:
        """Get statistics about the preview queue"""
        self.preview_queue = self._load_preview_queue()

        stats: dict[str, Any] = {
            "total": len(self.preview_queue),
            "pending_approval": 0,
            "approved": 0,
            "rejected": 0,
            "sent": 0,
            "would_send": 0,
            "by_template": {},
            "by_service": {},
        }

        for msg in self.preview_queue:
            status = msg.get("status", "unknown")
            if status in stats:
                stats[status] += 1

            # Count by template
            template_id = msg.get("template_id", "unknown")
            if template_id not in stats["by_template"]:
                stats["by_template"][template_id] = 0
            stats["by_template"][template_id] += 1

            # Count by service
            service_name = msg.get("service_name", "Unknown")
            if service_name not in stats["by_service"]:
                stats["by_service"][service_name] = 0
            stats["by_service"][service_name] += 1

        return stats

    def cleanup_old_messages(self, days_old: int = 30) -> dict:
        """Remove messages older than specified days"""
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_old)
        removed_count = 0
        new_queue = []

        for msg in self.preview_queue:
            created_at = msg.get("created_at", "")
            try:
                msg_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if msg_date > cutoff_date:
                    new_queue.append(msg)
                else:
                    removed_count += 1
            except Exception:
                new_queue.append(msg)  # Keep if can't parse date

        self.preview_queue = new_queue
        self._save_preview_queue()

        return {"success": True, "removed_count": removed_count}


# Singleton instance
message_preview_service = MessagePreviewService()
