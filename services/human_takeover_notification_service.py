# services/human_takeover_notification_service.py
"""
Human Takeover Notification Service
Sends WhatsApp template notifications to admin/staff when a conversation is escalated
"""

import re
from typing import List, Dict, Any, Optional
from services.montymobile_template_service import montymobile_template_service
from services.api_integrations import log_report_event


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
        "negative_sentiment_detected": "مشاعر سلبية"
    }
    
    def __init__(self):
        self.template_id = "human_takeover_alert"
        print(f"✅ Human Takeover Notification Service initialized")
    
    def get_escalation_reason_arabic(self, reason: str) -> str:
        """Convert English escalation reason to Arabic"""
        return self.ESCALATION_REASON_AR.get(reason, reason)
    
    def parse_mobile_numbers(self, mobile_numbers_string: str) -> List[str]:
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
        numbers = []
        seen_numbers = set()
        for number in re.split(r"[,;\n]+", mobile_numbers_string):
            cleaned = number.strip()
            if cleaned:
                # Keep only digits and leading plus
                cleaned = re.sub(r"[^\d+]", "", cleaned)
                if cleaned.startswith("00"):
                    cleaned = "+" + cleaned[2:]

                # Ensure number starts with +
                if not cleaned.startswith('+'):
                    # Assume Lebanon country code if not provided
                    if cleaned.startswith('961'):
                        cleaned = '+' + cleaned
                    elif cleaned.startswith('0'):
                        # Remove leading 0 and add +961
                        cleaned = '+961' + cleaned[1:]
                    else:
                        # Add +961 prefix
                        cleaned = '+961' + cleaned
                if cleaned not in seen_numbers:
                    seen_numbers.add(cleaned)
                    numbers.append(cleaned)
        
        return numbers
    
    async def send_notification(
        self,
        customer_name: str,
        customer_phone: str,
        escalation_reason: str,
        last_message: str,
        notify_numbers: List[str]
    ) -> Dict[str, Any]:
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
            print(f"⚠️ No notification numbers configured for human takeover alerts")
            return {
                "success": False,
                "error": "No notification numbers configured",
                "sent_count": 0
            }
        
        # Translate escalation reason to Arabic
        escalation_reason_ar = self.get_escalation_reason_arabic(escalation_reason)
        
        # Truncate last message to 100 characters
        last_message_truncated = last_message[:100] + "..." if len(last_message) > 100 else last_message
        
        # Prepare template parameters
        parameters = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "escalation_reason": escalation_reason_ar,
            "last_message": last_message_truncated
        }
        
        print(f"📤 Sending human takeover notifications to {len(notify_numbers)} number(s)")
        print(f"   Customer: {customer_name} ({customer_phone})")
        print(f"   Reason: {escalation_reason} → {escalation_reason_ar}")
        print(f"   Notify: {', '.join(notify_numbers)}")
        
        results = []
        success_count = 0
        
        # Send to each number
        for phone_number in notify_numbers:
            try:
                result = await montymobile_template_service.send_template_message(
                    template_id=self.template_id,
                    phone_number=phone_number,
                    language="ar",
                    parameters=parameters
                )
                
                if result.get("success"):
                    success_count += 1
                    print(f"   ✅ Sent to {phone_number}")
                else:
                    print(f"   ❌ Failed to send to {phone_number}: {result.get('error')}")
                
                results.append({
                    "phone_number": phone_number,
                    "success": result.get("success", False),
                    "message_id": result.get("message_id"),
                    "error": result.get("error")
                })
                
            except Exception as e:
                print(f"   ❌ Exception sending to {phone_number}: {e}")
                results.append({
                    "phone_number": phone_number,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "success": success_count > 0,
            "sent_count": success_count,
            "total_numbers": len(notify_numbers),
            "results": results
        }
    
    async def notify_from_settings(
        self,
        customer_name: str,
        customer_phone: str,
        escalation_reason: str,
        last_message: str,
        settings_mobile_numbers: str
    ) -> Dict[str, Any]:
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
            print(f"⚠️ No valid mobile numbers found in settings")
            return {
                "success": False,
                "error": "No valid mobile numbers configured",
                "sent_count": 0
            }
        
        # Send notifications
        return await self.send_notification(
            customer_name=customer_name,
            customer_phone=customer_phone,
            escalation_reason=escalation_reason,
            last_message=last_message,
            notify_numbers=notify_numbers
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
        conversation_id: Optional[str] = None,
        settings_mobile_numbers: Optional[str] = None,
        extra_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Unified AI->Human handoff flow:
        1) Notifies configured admin numbers
        2) Writes an audit event with notification outcome
        """
        if settings_mobile_numbers is None:
            from services.settings_service import settings_service
            settings_mobile_numbers = settings_service.get_human_takeover_notify_mobiles()

        notification_result = await self.notify_from_settings(
            customer_name=customer_name,
            customer_phone=customer_phone,
            escalation_reason=escalation_reason,
            last_message=last_message,
            settings_mobile_numbers=settings_mobile_numbers
        )

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
            "notification_error": notification_result.get("error")
        }
        if extra_details:
            audit_details.update(extra_details)

        log_report_event(
            "human_handover_audit",
            user_id or customer_phone or "unknown_user",
            user_gender or "unknown",
            audit_details
        )

        return {
            "success": notification_result.get("success", False),
            "notification_result": notification_result,
            "audit_event": "human_handover_audit"
        }


# Global instance
human_takeover_notification_service = HumanTakeoverNotificationService()
