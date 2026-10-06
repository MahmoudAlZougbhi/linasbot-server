"""
Human Takeover Notification Service
Sends WhatsApp template notifications to admin/staff when a conversation is escalated
"""

from __future__ import annotations

# services/live_chat/human_takeover_notification_service.py
from typing import Any

from services.saas_no_boc import log_report_event


class HumanTakeoverNotificationService:
    """Service for notifying admins about human takeover requests"""

    # Mapping of escalation reasons to Arabic translations
    ESCALATION_REASON_AR = {
        "customer_requested_human": "طلب التحدث مع موظف",
        "offensive_language_detected": "لغة غير لائقة",
        "customer_angry": "العميل غاضب",
        "bot_unable_to_help": "البوت غير قادر على المساعدة",
        "customer_confused": "العميل محتار",
        "urgent_request": "طلب عاجل",
        "customer_frustrated": "العميل محبط",
        "negative_sentiment_detected": "مشاعر سلبية",
    }

    def __init__(self) -> None:
        self.template_id = "human_takeover_alert"
        print("✅ Human Takeover Notification Service initialized")

    def get_escalation_reason_arabic(self, reason: str) -> str:
        """Convert English escalation reason to Arabic"""
        return self.ESCALATION_REASON_AR.get(reason, reason)

    def parse_mobile_numbers(self, mobile_numbers_string: str) -> list[str]:
        """
        Parse comma-separated mobile numbers string

        Args:
            mobile_numbers_string: Comma-separated phone numbers

        Returns:
            List of cleaned phone numbers
        """
        if not mobile_numbers_string or not mobile_numbers_string.strip():
            return []

        # Split by common separators and clean each number
        from services.live_chat.staff_alert_numbers import parse_e164_list

        return parse_e164_list(mobile_numbers_string)

    async def send_notification(
        self,
        customer_name: str,
        customer_phone: str,
        escalation_reason: str,
        last_message: str,
        notify_numbers: list[str],
    ) -> dict[str, Any]:
        """
        Send human takeover notification to admin numbers

        Args:
            customer_name: Name of the customer
            customer_phone: Customer's phone number
            escalation_reason: Reason for escalation (English key)
            last_message: Last message from customer
            notify_numbers: List of phone numbers to notify

        Returns:
            Dict with success status and results
        """
        if not notify_numbers:
            print("⚠️ No notification numbers configured for human takeover alerts")
            return {"success": False, "error": "No notification numbers configured", "sent_count": 0}

        # Translate escalation reason to Arabic
        escalation_reason_ar = self.get_escalation_reason_arabic(escalation_reason)

        # Truncate last message to 100 characters
        last_message_truncated = last_message[:100] + "..." if len(last_message) > 100 else last_message

        # Prepare template parameters
        parameters = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "escalation_reason": escalation_reason_ar,
            "last_message": last_message_truncated,
        }

        del parameters, escalation_reason_ar, customer_name, customer_phone
        return {
            "success": False,
            "error": "tenant_delivery_unavailable",
            "sent_count": 0,
            "total_numbers": len(notify_numbers),
            "results": [],
        }

    async def notify_from_settings(
        self,
        customer_name: str,
        customer_phone: str,
        escalation_reason: str,
        last_message: str,
        settings_mobile_numbers: str,
    ) -> dict[str, Any]:
        """
        Send notification using mobile numbers from settings

        Args:
            customer_name: Name of the customer
            customer_phone: Customer's phone number
            escalation_reason: Reason for escalation
            last_message: Last message from customer
            settings_mobile_numbers: Comma-separated mobile numbers from settings

        Returns:
            Dict with success status and results
        """
        # Parse mobile numbers from settings
        notify_numbers = self.parse_mobile_numbers(settings_mobile_numbers)

        if not notify_numbers:
            print("⚠️ No valid mobile numbers found in settings")
            return {"success": False, "error": "No valid mobile numbers configured", "sent_count": 0}

        # Send notifications
        return await self.send_notification(
            customer_name=customer_name,
            customer_phone=customer_phone,
            escalation_reason=escalation_reason,
            last_message=last_message,
            notify_numbers=notify_numbers,
        )

    async def notify_and_audit_handoff(
        self,
        user_id: str,
        user_gender: str,
        customer_name: str,
        customer_phone: str,
        escalation_reason: str,
        last_message: str,
        trigger_source: str,
        conversation_id: str | None = None,
        settings_mobile_numbers: str | None = None,
        extra_details: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any]:
        """
        Unified AI->Human handoff flow:
        1) Notifies configured admin numbers
        2) Writes an audit event with notification outcome
        3) Persists an in-app owner alert (Linas AI Notifications inbox)
        """
        from services.live_chat.staff_alert_numbers import load_staff_alerts
        from services.live_chat.staff_alert_transport import deliver_staff_whatsapp

        alerts = load_staff_alerts(str(tenant_id or ""))
        notification_result = await deliver_staff_whatsapp(
            tenant_id=str(tenant_id or ""),
            numbers=list(alerts["numbers"]),
            template_name=str(alerts["template_name"]),
            template_language=str(alerts["template_language"]),
            parameters={
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "escalation_reason": escalation_reason,
                "last_message": (last_message or "")[:100],
            },
        )
        del settings_mobile_numbers

        audit_details = {
            "trigger_source": trigger_source,
            "conversation_id": conversation_id,
            "escalation_reason": escalation_reason,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "last_message": (last_message or "")[:250],
            "notification_success": notification_result.get("success", False),
            "notification_sent_count": notification_result.get("sent_count", 0),
            "notification_total_numbers": notification_result.get("total_numbers", 0),
            "notification_error": notification_result.get("error"),
        }
        if extra_details:
            audit_details.update(extra_details)

        log_report_event(
            "human_handover_audit", user_id or customer_phone or "unknown_user", user_gender or "unknown", audit_details
        )

        owner_alert = None
        try:
            from services.owner_copilot.owner_alert_service import owner_alert_service

            resolved_tenant = tenant_id
            resolved_channel = channel
            if extra_details:
                if not resolved_tenant:
                    resolved_tenant = extra_details.get("tenant_id")
                if not resolved_channel:
                    resolved_channel = extra_details.get("channel")
            owner_alert = owner_alert_service.emit_handoff(
                tenant_id=resolved_tenant,
                customer_name=customer_name,
                user_id=user_id,
                conversation_id=conversation_id,
                channel=resolved_channel,
                escalation_reason=escalation_reason,
                last_message=last_message,
                trigger_source=trigger_source,
            )
        except Exception as alert_err:
            print(f"⚠️ Failed to persist owner alert for handoff: {alert_err}")

        return {
            "success": notification_result.get("success", False),
            "notification_result": notification_result,
            "audit_event": "human_handover_audit",
            "owner_alert_id": (owner_alert or {}).get("id"),
        }


# Global instance
human_takeover_notification_service = HumanTakeoverNotificationService()
