# Scheduled Messages Collector Service
# Collects all future appointments and generates to-be-sent messages log
# Saves to data/scheduled_messages_to_be_sent.json

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from services.api_integrations import get_customer_appointments, get_all_customers

class ScheduledMessagesCollector:
    """
    Collects all appointments that qualify for Smart Messaging and generates a log
    of messages that will be sent in the future.
    
    Message types collected:
    1. 24-Hour Reminder: Appointments 24+ hours in future (send 24h before)
    2. Same-Day Check-in: Appointments tomorrow (send tomorrow at 7 AM)
    3. Post-Session Feedback: Appointments ended <2 hours ago (send 2h after)
    4. No-Show Follow-up: Missed appointments <1 hour passed (send 1h after)
    5. 1-Month Follow-up: Attended appointments 30+ days passed (send 30d after)
    6. Missed Yesterday: Missed appointments 24-48 hours passed
    7. Missed This Month: Missed appointments 30+ days passed
    8. Attended Yesterday: Attended appointments 24h passed (not missed)
    """
    
    def __init__(self):
        self.log_file = 'data/scheduled_messages_to_be_sent.json'
        self.messages_to_send = []
        
    def load_or_create_log(self) -> List[Dict]:
        """Load existing log or create new one"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"❌ Error loading scheduled messages log: {e}")
                return []
        return []
    
    def save_log(self, messages: List[Dict]):
        """Save messages log to file"""
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            print(f"✅ Saved {len(messages)} scheduled messages to {self.log_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving scheduled messages log: {e}")
            return False
    
    async def collect_all_scheduled_messages(self) -> List[Dict]:
        """
        Collect all future appointments and generate to-be-sent messages
        Returns list of messages to be sent with structure:
        {
            "appointment_id": str,
            "customer_name": str,
            "customer_phone": str,
            "message_type": str,
            "send_datetime": str,  # ISO format
            "status": "pending",
            "error": null or str,
            "appointment_datetime": str,
            "appointment_status": str,  # "Available", "Done", "Missed", etc.
            "created_at": str,
            "last_updated": str
        }
        """
        print("\n" + "="*80)
        print("🔄 COLLECTING SCHEDULED MESSAGES TO BE SENT")
        print("="*80)
        
        current_time = datetime.now()
        messages_to_send = []
        
        try:
            # Get all customers
            customers_response = await get_all_customers()
            if not customers_response.get('success'):
                print(f"❌ Failed to get customers: {customers_response.get('message')}")
                return messages_to_send
            
            customers = customers_response.get('data', [])
            print(f"🔍 Found {len(customers)} customers")
            
            # For each customer, get their appointments
            for customer in customers:
                customer_id = customer.get('id')
                customer_name = customer.get('name', 'Unknown')
                customer_phone = customer.get('phone', '')
                
                # Get appointments for this customer
                appointments_response = await get_customer_appointments(customer_phone)
                if not appointments_response.get('success'):
                    print(f"⚠️ Failed to get appointments for {customer_name}")
                    continue
                
                appointments = appointments_response.get('data', [])
                print(f"\n📅 Customer: {customer_name} ({customer_phone})")
                print(f"   Found {len(appointments)} appointments")
                
                # Analyze each appointment
                for apt in appointments:
                    apt_id = apt.get('id')
                    apt_date = apt.get('date')  # Format: YYYY-MM-DD
                    apt_time = apt.get('time', '00:00')  # Format: HH:MM
                    apt_status = apt.get('status', 'Available')  # Available, Done, Missed, etc.
                    
                    try:
                        apt_datetime = datetime.fromisoformat(f"{apt_date}T{apt_time}")
                    except:
                        print(f"   ⚠️ Invalid appointment datetime: {apt_date} {apt_time}")
                        continue
                    
                    # Calculate time differences
                    time_until_apt = apt_datetime - current_time
                    time_since_apt = current_time - apt_datetime
                    
                    messages = self._generate_messages_for_appointment(
                        apt_id, customer_name, customer_phone,
                        apt_datetime, apt_status, current_time, time_until_apt, time_since_apt
                    )
                    
                    messages_to_send.extend(messages)
            
            # Save all collected messages
            self.save_log(messages_to_send)
            
            print("\n" + "="*80)
            print(f"✅ COLLECTION COMPLETE: {len(messages_to_send)} messages to be sent")
            print("="*80)
            
            return messages_to_send
            
        except Exception as e:
            print(f"❌ Error collecting scheduled messages: {e}")
            import traceback
            traceback.print_exc()
            return messages_to_send
    
    def _generate_messages_for_appointment(
        self,
        apt_id: str,
        customer_name: str,
        customer_phone: str,
        apt_datetime: datetime,
        apt_status: str,
        current_time: datetime,
        time_until_apt: timedelta,
        time_since_apt: timedelta
    ) -> List[Dict]:
        """Generate all applicable messages for an appointment"""
        messages = []
        
        # 1. 24-Hour Reminder
        # Collects: Appointments 24+ hours in future
        # Send time: 24 hours before appointment
        if time_until_apt.total_seconds() > 86400:  # More than 24 hours away
            send_datetime = apt_datetime - timedelta(hours=24)
            if send_datetime > current_time:  # Only if send time is in future
                messages.append({
                    "appointment_id": apt_id,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "message_type": "reminder_24h",
                    "reason": "24-Hour Appointment Reminder",
                    "send_datetime": send_datetime.isoformat(),
                    "status": "pending",
                    "error": None,
                    "appointment_datetime": apt_datetime.isoformat(),
                    "appointment_status": apt_status,
                    "created_at": current_time.isoformat(),
                    "last_updated": current_time.isoformat()
                })
        
        # 2. Same-Day Check-in
        # Collects: Appointments tomorrow (if status is "Available")
        # Send time: Tomorrow at 7 AM
        if apt_status.lower() == 'available':
            tomorrow = (current_time + timedelta(days=1)).date()
            apt_date = apt_datetime.date()
            if apt_date == tomorrow:
                send_datetime = current_time.replace(hour=7, minute=0, second=0, microsecond=0)
                if send_datetime < current_time:  # If already past 7 AM today
                    send_datetime += timedelta(days=1)
                messages.append({
                    "appointment_id": apt_id,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "message_type": "same_day_checkin",
                    "reason": "Same-Day Check-in Reminder",
                    "send_datetime": send_datetime.isoformat(),
                    "status": "pending",
                    "error": None,
                    "appointment_datetime": apt_datetime.isoformat(),
                    "appointment_status": apt_status,
                    "created_at": current_time.isoformat(),
                    "last_updated": current_time.isoformat()
                })
        
        # 3. Post-Session Feedback
        # Collects: Appointments ended but <2 hours ago (if status is "Done")
        # Send time: 2 hours after appointment
        if apt_status.lower() == 'done':
            if 0 < time_since_apt.total_seconds() < 7200:  # Less than 2 hours passed
                send_datetime = apt_datetime + timedelta(hours=2)
                if send_datetime > current_time:  # Only if send time is in future
                    messages.append({
                        "appointment_id": apt_id,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                        "message_type": "post_session_feedback",
                        "reason": "Post-Session Feedback Request",
                        "send_datetime": send_datetime.isoformat(),
                        "status": "pending",
                        "error": None,
                        "appointment_datetime": apt_datetime.isoformat(),
                        "appointment_status": apt_status,
                        "created_at": current_time.isoformat(),
                        "last_updated": current_time.isoformat()
                    })
        
        # 4. No-Show Follow-up
        # Collects: Missed appointments <1 hour passed (if status is "Missed")
        # Send time: 1 hour after appointment
        if apt_status.lower() == 'missed':
            if 0 < time_since_apt.total_seconds() < 3600:  # Less than 1 hour passed
                send_datetime = apt_datetime + timedelta(hours=1)
                if send_datetime > current_time:  # Only if send time is in future
                    messages.append({
                        "appointment_id": apt_id,
                        "customer_name": customer_name,
                        "customer_phone": customer_phone,
                        "message_type": "no_show_followup",
                        "reason": "No-Show Follow-up",
                        "send_datetime": send_datetime.isoformat(),
                        "status": "pending",
                        "error": None,
                        "appointment_datetime": apt_datetime.isoformat(),
                        "appointment_status": apt_status,
                        "created_at": current_time.isoformat(),
                        "last_updated": current_time.isoformat()
                    })
        
        # 5. 1-Month Follow-up
        # Collects: Attended appointments 30+ days passed (if status is "Done")
        # Send time: 30 days after appointment
        if apt_status.lower() == 'done':
            if time_since_apt.total_seconds() >= 2592000:  # 30 days passed
                if time_since_apt.total_seconds() < 2678400:  # But not more than 31 days (prevent resending)
                    send_datetime = apt_datetime + timedelta(days=30)
                    if send_datetime > current_time:  # Only if send time is in future (shouldn't happen)
                        messages.append({
                            "appointment_id": apt_id,
                            "customer_name": customer_name,
                            "customer_phone": customer_phone,
                            "message_type": "one_month_followup",
                            "reason": "One-Month Follow-up",
                            "send_datetime": send_datetime.isoformat(),
                            "status": "pending",
                            "error": None,
                            "appointment_datetime": apt_datetime.isoformat(),
                            "appointment_status": apt_status,
                            "created_at": current_time.isoformat(),
                            "last_updated": current_time.isoformat()
                        })
        
        # 6. Missed Yesterday (Optional - varies constantly)
        # Collects: Missed appointments 24-48 hours passed
        # Note: This varies too much. Can skip file persistence if you prefer.
        
        # 7. Missed This Month (Optional - varies constantly)
        # Collects: Missed appointments 30+ days passed
        # Note: This varies too much. Can skip file persistence if you prefer.
        
        # 8. Attended Yesterday (Optional - varies constantly)
        # Collects: Attended appointments 24+ hours passed
        # Note: This varies too much. Can skip file persistence if you prefer.
        
        return messages
    
    def get_pending_messages(self) -> List[Dict]:
        """Get all pending messages that should be sent now"""
        try:
            messages = self.load_or_create_log()
            current_time = datetime.now()
            
            pending = []
            for msg in messages:
                if msg.get('status') == 'pending':
                    try:
                        send_time = datetime.fromisoformat(msg.get('send_datetime', ''))
                        if send_time <= current_time:
                            pending.append(msg)
                    except:
                        pass
            
            return pending
        except Exception as e:
            print(f"❌ Error getting pending messages: {e}")
            return []
    
    def mark_message_sent(self, message_id: str):
        """Mark a message as sent in the log"""
        try:
            messages = self.load_or_create_log()
            current_time = datetime.now()
            
            for msg in messages:
                if msg.get('appointment_id') == message_id:
                    msg['status'] = 'sent'
                    msg['last_updated'] = current_time.isoformat()
                    break
            
            self.save_log(messages)
            return True
        except Exception as e:
            print(f"❌ Error marking message as sent: {e}")
            return False
    
    def mark_message_failed(self, message_id: str, error: str):
        """Mark a message as failed in the log"""
        try:
            messages = self.load_or_create_log()
            current_time = datetime.now()
            
            for msg in messages:
                if msg.get('appointment_id') == message_id:
                    msg['status'] = 'failed'
                    msg['error'] = error
                    msg['last_updated'] = current_time.isoformat()
                    break
            
            self.save_log(messages)
            return True
        except Exception as e:
            print(f"❌ Error marking message as failed: {e}")
            return False


# Export singleton instance
scheduled_messages_collector = ScheduledMessagesCollector()
