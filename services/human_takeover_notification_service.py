# services/human_takeover_notification_service.py
"""
Human Takeover Notification Service
Sends WhatsApp template notifications to admin/staff when a conversation is escalated
"""

from typing import List, Dict, Any
from services.montymobile_template_service import montymobile_template_service


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
        
        # Split by comma and clean each number
        numbers = []
        for number in mobile_numbers_string.split(','):
            cleaned = number.strip()
            if cleaned:
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


# Global instance
human_takeover_notification_service = HumanTakeoverNotificationService()
