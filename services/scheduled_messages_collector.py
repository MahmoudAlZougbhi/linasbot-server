from __future__ import annotations

# Scheduled Messages Collector Service
# Collects all future appointments and generates to-be-sent messages log
# Saves to data/scheduled_messages_to_be_sent.json
# Uses send_appointment_reminders (by date/status) since get_all_customers is not available in the API.
import json
import os
from datetime import datetime, timedelta
from typing import Any, cast

from services.api_integrations import send_appointment_reminders


def _extract_appointments(result: dict) -> list[dict]:
    """Extract appointments list from API response."""
    if not isinstance(result, dict) or not result.get("success"):
        return []
    data = result.get("data", {})
    if isinstance(data, dict):
        return data.get("appointments", []) or []
    if isinstance(data, list):
        return data
    return []


def _parse_apt_datetime(apt: dict) -> datetime | None:
    """Parse appointment datetime from reminders API or customer appointments format."""
    # Format 1: appointment_details.date (e.g. "15/01/2026 10:00:00 AM" or "2026-01-15 10:00:00")
    apt_details = apt.get("appointment_details") or {}
    if isinstance(apt_details, dict):
        date_str = apt_details.get("date")
        if date_str:
            s = str(date_str).strip()
            for fmt in (
                "%d/%m/%Y %I:%M:%S %p",
                "%d/%m/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    return datetime.strptime(s, fmt)
                except (ValueError, TypeError):
                    continue
    # Format 2: date + time fields (YYYY-MM-DD, HH:MM)
    apt_date = apt.get("date")
    apt_time = apt.get("time", "00:00")
    if apt_date:
        try:
            return datetime.fromisoformat(f"{apt_date}T{apt_time}")
        except (ValueError, TypeError):
            pass
    return None


def _normalize_apt_for_collector(apt: dict) -> dict | None:
    """Convert reminders API format to collector format (id, date, time, status, phone, name)."""
    apt_details = apt.get("appointment_details") or {}
    if isinstance(apt_details, dict):
        apt_id = apt_details.get("id") or apt.get("appointment_id")
        apt_datetime = _parse_apt_datetime(apt)
        if not apt_datetime:
            return None
        # Map API status to collector status
        status = str(apt.get("status") or apt_details.get("status") or "Available").strip()
        customer_phone = apt.get("phone") or ""
        customer_name = apt.get("name") or "Unknown"
        return {
            "id": apt_id,
            "date": apt_datetime.strftime("%Y-%m-%d"),
            "time": apt_datetime.strftime("%H:%M"),
            "status": status,
            "phone": customer_phone,
            "name": customer_name,
            "apt_datetime": apt_datetime,
        }
    # Already in customer appointments format
    apt_date = apt.get("date")
    apt_time = apt.get("time", "00:00")
    apt_datetime = _parse_apt_datetime(apt)
    if not apt_datetime:
        return None
    return {
        "id": apt.get("id"),
        "date": apt_date,
        "time": apt_time,
        "status": apt.get("status", "Available"),
        "phone": apt.get("phone", ""),
        "name": apt.get("name", "Unknown"),
        "apt_datetime": apt_datetime,
    }


class ScheduledMessagesCollector:
    """
    Collects all appointments that qualify for Smart Messaging and generates a log
    of messages that will be sent in the future.

    Message types collected:
    1. 24-Hour Reminder: Appointments 24+ hours in future (send 24h before)
    2. Post Session Feedback: Appointments ended <2 hours ago (send 2h after)
    3. 1-Month Follow-up: Attended appointments 30+ days passed (send 30d after)
    4. Missed Yesterday: Missed appointments 24-48 hours passed
    5. Missed This Month: Missed appointments 30+ days passed
    6. session_feedback (Meta): next-day Done — handled by daily dispatcher, not collector
    """

    def __init__(self) -> None:
        from storage.persistent_storage import SCHEDULED_MESSAGES_FILE, ensure_dirs

        ensure_dirs()
        self.log_file = str(SCHEDULED_MESSAGES_FILE)
        self.messages_to_send: list[dict[str, Any]] = []

    def load_or_create_log(self) -> list[dict]:
        """Load existing log or create new one"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, encoding="utf-8") as f:
                    return cast(list[dict[Any, Any]], json.load(f))
            except Exception as e:
                print(f"❌ Error loading scheduled messages log: {e}")
                return []
        return []

    def save_log(self, messages: list[dict]) -> Any:
        """Save messages log to file"""
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            print(f"✅ Saved {len(messages)} scheduled messages to {self.log_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving scheduled messages log: {e}")
            return False

    async def collect_all_scheduled_messages(self) -> list[dict]:
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
        print("\n" + "=" * 80)
        print("🔄 COLLECTING SCHEDULED MESSAGES TO BE SENT")
        print("=" * 80)

        current_time = datetime.now()
        messages_to_send = []
        seen_keys = set()  # Avoid duplicates (same apt from multiple status calls)

        try:
            # Use send_appointment_reminders by date (API has no get_all_customers)
            # Scan date range: 2 days ago to 35 days ahead
            start_date = (current_time - timedelta(days=2)).date()
            end_date = (current_time + timedelta(days=35)).date()
            total_appointments = 0

            d = start_date
            while d <= end_date:
                date_str = d.strftime("%Y-%m-%d")
                result = await send_appointment_reminders(date=date_str)
                appointments = _extract_appointments(result)
                for apt in appointments:
                    norm = _normalize_apt_for_collector(apt)
                    if not norm or not norm.get("phone"):
                        continue
                    key = (norm.get("id"), norm["date"], norm["time"], norm.get("phone", ""))
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    total_appointments += 1
                    apt_datetime = norm["apt_datetime"]
                    time_until_apt = apt_datetime - current_time
                    time_since_apt = current_time - apt_datetime
                    messages = self._generate_messages_for_appointment(
                        norm.get("id") or "",
                        norm["name"],
                        norm["phone"],
                        apt_datetime,
                        norm["status"],
                        current_time,
                        time_until_apt,
                        time_since_apt,
                    )
                    messages_to_send.extend(messages)
                d += timedelta(days=1)

            print(f"🔍 Scanned {total_appointments} unique appointments from reminders API")

            # Save all collected messages
            self.save_log(messages_to_send)

            print("\n" + "=" * 80)
            print(f"✅ COLLECTION COMPLETE: {len(messages_to_send)} messages to be sent")
            print("=" * 80)

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
        time_since_apt: timedelta,
    ) -> list[dict]:
        """Generate all applicable messages for an appointment"""
        messages = []

        # 1. 24-Hour Reminder
        # Collects: Appointments 24+ hours in future
        # Send time: 24 hours before appointment
        if time_until_apt.total_seconds() > 86400:  # More than 24 hours away
            send_datetime = apt_datetime - timedelta(hours=24)
            if send_datetime > current_time:  # Only if send time is in future
                messages.append(
                    {
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
                        "last_updated": current_time.isoformat(),
                    }
                )

        # 2. Post Session Feedback
        # Collects: Appointments ended but <2 hours ago (if status is "Done")
        # Send time: 2 hours after appointment
        if apt_status.lower() == "done":
            if 0 < time_since_apt.total_seconds() < 7200:  # Less than 2 hours passed
                send_datetime = apt_datetime + timedelta(hours=2)
                if send_datetime > current_time:  # Only if send time is in future
                    messages.append(
                        {
                            "appointment_id": apt_id,
                            "customer_name": customer_name,
                            "customer_phone": customer_phone,
                            "message_type": "thank_you_message_sent_after_session",
                            "reason": "Post Session Feedback Request",
                            "send_datetime": send_datetime.isoformat(),
                            "status": "pending",
                            "error": None,
                            "appointment_datetime": apt_datetime.isoformat(),
                            "appointment_status": apt_status,
                            "created_at": current_time.isoformat(),
                            "last_updated": current_time.isoformat(),
                        }
                    )

        # 3. 1-Month Follow-up
        # Collects: Attended appointments 17+ days passed (if status is "Done")
        # Send time: 17 days after appointment
        if apt_status.lower() == "done":
            if time_since_apt.total_seconds() >= 1468800:  # 17 days passed
                if time_since_apt.total_seconds() < 1555200:  # But not more than 18 days (prevent resending)
                    send_datetime = apt_datetime + timedelta(days=17)
                    if send_datetime > current_time:  # Only if send time is in future (shouldn't happen)
                        messages.append(
                            {
                                "appointment_id": apt_id,
                                "customer_name": customer_name,
                                "customer_phone": customer_phone,
                                "message_type": "sent_17_days_after_last_session_new",
                                "reason": "One-Month Follow-up",
                                "send_datetime": send_datetime.isoformat(),
                                "status": "pending",
                                "error": None,
                                "appointment_datetime": apt_datetime.isoformat(),
                                "appointment_status": apt_status,
                                "created_at": current_time.isoformat(),
                                "last_updated": current_time.isoformat(),
                            }
                        )

        # 4. session_feedback: REMOVED from collector (daily dispatcher).
        # Thank-you is sent only by daily_template_dispatcher at configured time (rule-based:
        # yesterday's DONE appointments). This prevents duplicate thank-you sends.

        return messages

    def get_pending_messages(self) -> list[dict]:
        """Get all pending messages that should be sent now"""
        try:
            messages = self.load_or_create_log()
            current_time = datetime.now()

            pending = []
            for msg in messages:
                if msg.get("status") == "pending":
                    try:
                        send_time = datetime.fromisoformat(msg.get("send_datetime", ""))
                        if send_time <= current_time:
                            pending.append(msg)
                    except Exception:
                        pass

            return pending
        except Exception as e:
            print(f"❌ Error getting pending messages: {e}")
            return []

    def mark_message_sent(self, message_id: str) -> Any:
        """Mark a message as sent in the log"""
        try:
            messages = self.load_or_create_log()
            current_time = datetime.now()

            for msg in messages:
                if msg.get("appointment_id") == message_id:
                    msg["status"] = "sent"
                    msg["last_updated"] = current_time.isoformat()
                    break

            self.save_log(messages)
            return True
        except Exception as e:
            print(f"❌ Error marking message as sent: {e}")
            return False

    def mark_message_failed(self, message_id: str, error: str) -> Any:
        """Mark a message as failed in the log"""
        try:
            messages = self.load_or_create_log()
            current_time = datetime.now()

            for msg in messages:
                if msg.get("appointment_id") == message_id:
                    msg["status"] = "failed"
                    msg["error"] = error
                    msg["last_updated"] = current_time.isoformat()
                    break

            self.save_log(messages)
            return True
        except Exception as e:
            print(f"❌ Error marking message as failed: {e}")
            return False


# Export singleton instance
scheduled_messages_collector = ScheduledMessagesCollector()
