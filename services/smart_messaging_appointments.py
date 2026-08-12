"""Smart messaging appointment reminder / cleanup mixin (LOC split)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.message_logs_service import message_logs_service
from services.smart_messaging_catalog import TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS, normalize_template_id


class SmartMessagingAppointmentsMixin:
    """Appointment reminder scheduling and daily cleanup."""

    scheduled_messages: dict[str, Any]

    _log_reminder_sent_analytics: Any
    _persist_sent_messages: Any
    schedule_message: Any

    def schedule_appointment_reminders(self, appointment_date: datetime, customer_data: dict) -> int:
        """Schedule all reminders for an appointment

        Returns:
            int: Number of messages scheduled
        """

        customer_phone = str(customer_data.get("phone") or "")
        if not customer_phone:
            return 0

        customer_name = customer_data.get("name", "عميلنا العزيز")
        language = customer_data.get("language", "ar")
        service_id = customer_data.get("service_id")
        service_name = customer_data.get("service", "جلسة ليزر")

        placeholders = {
            "customer_name": customer_name,
            "appointment_date": appointment_date.strftime("%Y-%m-%d"),
            "appointment_time": appointment_date.strftime("%H:%M"),
            "branch_name": customer_data.get("branch", "الفرع الرئيسي"),
            "service_name": service_name,
            "phone_number": "01234567",  # Support phone
        }
        raw_aid = customer_data.get("appointment_id")
        if raw_aid is not None:
            placeholders["appointment_id"] = raw_aid

        messages_scheduled = 0
        now = datetime.now()

        print(
            f"\n📋 Scheduling reminders for name_len={len(str(customer_name or ''))} (***{str(customer_phone)[-4:] if customer_phone else ''})"
        )
        print(f"   Appointment: {appointment_date}")
        print(f"   Current time: {now}")

        reminder_meta = {"source": "appointment_scheduler"}
        if raw_aid is not None:
            reminder_meta = {**reminder_meta, "appointment_id": raw_aid}

        # Schedule 24h reminder
        reminder_24h_time = appointment_date - timedelta(hours=24)
        if reminder_24h_time > now:
            result = self.schedule_message(
                customer_phone,
                "reminder_24h",
                reminder_24h_time,
                placeholders,
                language,
                service_id=service_id,
                service_name=service_name,
                metadata=reminder_meta,
            )
            if result:
                messages_scheduled += 1
                print(f"   ✅ reminder_24h scheduled for {reminder_24h_time}")
            else:
                print("   ❌ reminder_24h FAILED (returned None)")
        else:
            print(f"   ⏭️ reminder_24h SKIPPED (time {reminder_24h_time} is in the past)")

        # NOTE: thank_you_message_sent_after_session is handled by fixed-time daily jobs.

        # 17-day follow-up (Meta template sent_17_days_after_last_session_new)
        followup_time = appointment_date + timedelta(days=TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS)
        result = self.schedule_message(
            customer_phone,
            "sent_17_days_after_last_session_new",
            followup_time,
            placeholders,
            language,
            service_id=service_id,
            service_name=service_name,
            metadata={"source": "appointment_scheduler"},
        )
        if result:
            messages_scheduled += 1
            print(f"   ✅ sent_17_days_after_last_session_new scheduled for {followup_time}")
        else:
            print("   ❌ sent_17_days_after_last_session_new FAILED (returned None)")

        # NOTE: session_feedback (next day) is scheduled by daily_template_dispatcher
        # (yesterday + Done), not per-appointment here.

        print(f"   📊 Total scheduled: {messages_scheduled}\n")

        return messages_scheduled

    def get_scheduled_messages_summary(self) -> dict:
        """Get summary of scheduled messages"""

        summary: dict[str, Any] = {
            "total": len(self.scheduled_messages),
            "scheduled": 0,
            "sent": 0,
            "would_send": 0,
            "by_type": {},
            "next_message": None,
        }

        next_send_time = None

        for message_data in self.scheduled_messages.values():
            if message_data["status"] == "scheduled":
                summary["scheduled"] += 1

                # Find next message to be sent
                if not next_send_time or message_data["send_at"] < next_send_time:
                    next_send_time = message_data["send_at"]
                    summary["next_message"] = {
                        "type": message_data["message_type"],
                        "send_at": message_data["send_at"].isoformat(),
                        "phone": message_data["customer_phone"],
                    }
            elif message_data["status"] == "would_send":
                summary["would_send"] += 1
            else:
                summary["sent"] += 1

            # Count by type
            msg_type = message_data["message_type"]
            summary["by_type"][msg_type] = summary["by_type"].get(msg_type, 0) + 1

        return summary

    def mark_messages_sent_by_phone(self, customer_phone: str, message_type: str) -> int:
        """
        Mark all scheduled messages matching customer_phone + message_type as sent.
        Called by cron send jobs after successfully sending a message.

        Returns:
            int: Number of messages marked as sent
        """
        updated = 0
        now = datetime.now()

        # Normalize the input phone for comparison
        phone_clean = str(customer_phone).replace("+", "").replace(" ", "").replace("-", "")

        normalized_type = normalize_template_id(message_type)

        for message_id, msg_data in self.scheduled_messages.items():
            if normalize_template_id(msg_data.get("message_type")) != normalized_type:
                continue
            if msg_data.get("status") not in ("scheduled", "pending_approval"):
                continue

            # Normalize stored phone for comparison
            stored_phone = str(msg_data.get("customer_phone", "")).replace("+", "").replace(" ", "").replace("-", "")

            if stored_phone == phone_clean or stored_phone.endswith(phone_clean) or phone_clean.endswith(stored_phone):
                msg_data["status"] = "sent"
                msg_data["sent_at"] = now
                updated += 1
                metadata = msg_data.get("metadata", {}) if isinstance(msg_data.get("metadata"), dict) else {}
                reference_date = (
                    metadata.get("reference_date")
                    or msg_data.get("placeholders", {}).get("reference_date")
                    or msg_data.get("placeholders", {}).get("appointment_date")
                )
                appointment_id = metadata.get("appointment_id")
                customer_id = metadata.get("customer_id") or customer_phone
                campaign_id = metadata.get("campaign_id")

                try:
                    if not message_logs_service.was_message_sent(
                        customer_id=customer_id,
                        template_type=normalized_type,
                        reference_date=reference_date,
                        appointment_id=appointment_id,
                        campaign_id=campaign_id,
                    ):
                        message_logs_service.log_message(
                            customer_id=customer_id,
                            template_type=normalized_type,
                            appointment_id=appointment_id,
                            campaign_id=campaign_id,
                            reference_date=reference_date,
                            extra={
                                "phone": msg_data.get("customer_phone"),
                                "service_name": msg_data.get("service_name"),
                                "source": metadata.get("source", "sync_mark_sent"),
                            },
                        )
                except Exception as log_exc:
                    print(f"⚠️ Failed to write message log while syncing {message_id}: {log_exc}")
                self._log_reminder_sent_analytics(message_id, msg_data)
                print(f"   [SYNC] Marked {message_id} as sent in scheduled_messages dict")

        if updated == 0:
            print(
                f"   [SYNC] No matching scheduled message found for ***{str(customer_phone)[-4:] if customer_phone else ''} / {message_type}"
            )
        else:
            self._persist_sent_messages()

        return updated

    def clear_daily_messages(self) -> dict:
        """
        Clear stale messages from previous days.
        Called at the start of each day to refresh the dashboard.

        Rules:
        - Remove all messages where send_at date < today for MOST categories
        - KEEP all sent_17_days_after_last_session_new and sent_for_pause messages (they show
          cumulative data for the entire month)
        - KEEP messages sent today (so user can see what was sent)
        - Persist sent messages before clearing so history is not lost
        """
        preserved_types = {
            "sent_17_days_after_last_session_new",
            "sent_for_pause",
            "whatsapp_lead_no_booking",
        }
        today = datetime.now().date()

        # Persist sent messages first so they survive the cleanup
        self._persist_sent_messages()

        cleared = 0
        kept = 0
        new_scheduled = {}

        for message_id, msg_data in self.scheduled_messages.items():
            msg_type = normalize_template_id(msg_data.get("message_type", ""))

            # Always keep long-horizon follow-up and campaign messages
            if msg_type in preserved_types:
                new_scheduled[message_id] = msg_data
                kept += 1
                continue

            # Keep messages that were sent or dry-run today (so user can see today's activity)
            status = msg_data.get("status", "")
            sent_at = msg_data.get("sent_at")
            if status in ("sent", "would_send") and sent_at:
                sent_date = sent_at.date() if isinstance(sent_at, datetime) else None
                if sent_date and sent_date >= today:
                    new_scheduled[message_id] = msg_data
                    kept += 1
                    continue

            # Keep messages whose send_at is today or in the future
            send_at = msg_data.get("send_at")
            if send_at:
                send_date = send_at.date() if isinstance(send_at, datetime) else None
                if send_date and send_date >= today:
                    new_scheduled[message_id] = msg_data
                    kept += 1
                    continue

            # Otherwise, discard (stale message from a previous day)
            cleared += 1

        self.scheduled_messages = new_scheduled

        print(f"🧹 Daily cleanup: cleared {cleared} stale messages, kept {kept}")
        return {"cleared": cleared, "kept": kept}

    def cancel_scheduled_messages(self, customer_phone: str, message_type: str | None = None) -> Any:
        """Cancel scheduled messages for a customer"""

        cancelled = []
        for message_id, message_data in list(self.scheduled_messages.items()):
            if message_data["customer_phone"] == customer_phone and message_data["status"] == "scheduled":
                if not message_type or message_data["message_type"] == message_type:
                    self.scheduled_messages[message_id]["status"] = "cancelled"
                    cancelled.append(message_id)

        return cancelled
