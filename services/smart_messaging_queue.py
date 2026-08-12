"""Smart messaging persistence, schedule, preview, and send-state mixin (LOC split)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, cast

from services.message_logs_service import message_logs_service
from services.smart_messaging_catalog import normalize_template_id


class SmartMessagingQueueMixin:
    """Queue persistence and scheduled-message lifecycle."""

    # ------------------------------------------------------------------
    # Persistence helpers — keep queue + sent messages across restarts
    # ------------------------------------------------------------------

    def _deserialize_entry(self, entry: dict) -> dict:
        for key in ("send_at", "sent_at", "created_at", "last_attempt"):
            if entry.get(key):
                try:
                    entry[key] = datetime.fromisoformat(entry[key])
                except (ValueError, TypeError):
                    pass
        return entry

    def _serialize_entry(self, msg: dict) -> dict:
        entry = dict(msg)
        for key in ("send_at", "sent_at", "created_at", "last_attempt"):
            if isinstance(entry.get(key), datetime):
                entry[key] = entry[key].isoformat()
        return entry

    def _load_sent_messages(self) -> None:
        """Load previously sent messages from disk into scheduled_messages dict."""
        if not os.path.exists(self.SENT_MESSAGES_FILE):
            return
        try:
            with open(self.SENT_MESSAGES_FILE, encoding="utf-8") as f:
                entries = json.load(f)
            loaded = 0
            for message_id, entry in entries.items():
                self.scheduled_messages[message_id] = self._deserialize_entry(entry)
                loaded += 1
            print(f"✅ Loaded {loaded} sent messages from {self.SENT_MESSAGES_FILE}")
        except Exception as e:
            print(f"⚠️ Could not load sent messages: {e}")

    def _load_pending_queue(self) -> None:
        """Load non-terminal scheduled/pending/sending rows across restarts."""
        if not os.path.exists(self.QUEUE_FILE):
            return
        try:
            with open(self.QUEUE_FILE, encoding="utf-8") as f:
                entries = json.load(f)
            loaded = 0
            for message_id, entry in (entries or {}).items():
                status = (entry or {}).get("status")
                if status in ("sent", "would_send", "cancelled"):
                    continue
                # Prefer fresher in-memory/sent file if already present as terminal.
                existing = self.scheduled_messages.get(message_id)
                if existing and existing.get("status") in ("sent", "would_send"):
                    continue
                self.scheduled_messages[message_id] = self._deserialize_entry(dict(entry))
                loaded += 1
            print(f"✅ Loaded {loaded} pending smart messages from {self.QUEUE_FILE}")
        except Exception as e:
            print(f"⚠️ Could not load pending smart message queue: {e}")

    def _persist_sent_messages(self) -> None:
        """Save sent + pending queue so they survive restarts and multi-process reload."""
        try:
            sent_entries = {}
            pending_entries = {}
            for message_id, msg in self.scheduled_messages.items():
                status = msg.get("status")
                entry = self._serialize_entry(msg)
                if status in ("sent", "would_send"):
                    sent_entries[message_id] = entry
                elif status not in ("cancelled",):
                    pending_entries[message_id] = entry
            os.makedirs(os.path.dirname(self.SENT_MESSAGES_FILE), exist_ok=True)
            with open(self.SENT_MESSAGES_FILE, "w", encoding="utf-8") as f:
                json.dump(sent_entries, f, ensure_ascii=False, indent=2)
            os.makedirs(os.path.dirname(self.QUEUE_FILE), exist_ok=True)
            with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(pending_entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Could not persist smart messages: {e}")

    def schedule_message(
        self,
        customer_phone: str,
        message_type: str,
        send_at: datetime,
        placeholders: dict[str, str],
        language: str = "ar",
        service_id: int | None = None,
        service_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Schedule a message to be sent at specific time with service context"""

        canonical_type = normalize_template_id(message_type)
        message_id = f"{canonical_type}_{customer_phone}_{send_at.timestamp()}"

        # Check service-template mapping
        if service_id and not self._is_template_enabled_for_service(service_id, canonical_type):
            print(f"Template {canonical_type} not enabled for service {service_id}, skipping")
            return None

        meta = dict(metadata or {})
        self.scheduled_messages[message_id] = {
            "customer_phone": customer_phone,
            "message_type": canonical_type,
            "send_at": send_at,
            "placeholders": placeholders,
            "language": language,
            "service_id": service_id,
            "service_name": service_name or "Unknown Service",
            "status": "scheduled",
            "created_at": datetime.now(),
            "metadata": meta,
        }

        # Preview mode: every automated row requires explicit approval (no source bypass).
        if self._is_preview_mode_enabled() and meta.get("skip_preview") is not True:
            self._add_to_preview_queue(message_id)

        self._persist_sent_messages()
        return message_id

    def _is_smart_messaging_enabled(self) -> bool:
        """Check if smart messaging is globally enabled"""
        try:
            settings_file = self.settings_file
            if os.path.exists(settings_file):
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)
                return cast(bool, settings.get("smartMessaging", {}).get("enabled", True))
        except Exception as e:
            print(f"Error checking smart messaging status: {e}")
        return True

    def _is_preview_mode_enabled(self) -> bool:
        """Check if preview before send is enabled"""
        try:
            settings_file = self.settings_file
            if os.path.exists(settings_file):
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)
                return cast(bool, settings.get("smartMessaging", {}).get("previewBeforeSend", False))
        except Exception as e:
            print(f"Error checking preview mode: {e}")
        return False

    def _is_template_enabled_for_service(self, service_id: int, template_id: str) -> bool:
        """Check if template is enabled for a specific service"""
        try:
            template_id = normalize_template_id(template_id)
            mapping_file = self.mapping_file
            if os.path.exists(mapping_file):
                with open(mapping_file, encoding="utf-8") as f:
                    mappings = json.load(f)
                service_key = str(service_id)
                service_mapping = mappings.get("service_mappings", {}).get(service_key, {})
                templates = service_mapping.get("templates", {})
                return cast(bool, templates.get(template_id, True))
        except Exception as e:
            print(f"Error checking service-template mapping: {e}")
        return True

    def _add_to_preview_queue(self, message_id: str) -> None:
        """Add scheduled message to preview queue"""
        try:
            from services.message_preview_service import message_preview_service

            msg_data = self.scheduled_messages.get(message_id)
            if msg_data:
                # Update status to pending_approval
                self.scheduled_messages[message_id]["status"] = "pending_approval"

                # Add to preview service
                message_preview_service.add_to_preview_queue(
                    {
                        "message_id": message_id,
                        "customer_phone": msg_data.get("customer_phone"),
                        "customer_name": msg_data.get("placeholders", {}).get("customer_name", "Unknown"),
                        "template_id": msg_data.get("message_type"),
                        "language": msg_data.get("language", "ar"),
                        "placeholders": msg_data.get("placeholders", {}),
                        "service_id": msg_data.get("service_id"),
                        "service_name": msg_data.get("service_name", "Unknown Service"),
                        "scheduled_send_time": msg_data.get("send_at"),
                    }
                )
        except Exception as e:
            print(f"Error adding to preview queue: {e}")

    def _release_stuck_sending_messages(self, now: datetime) -> int:
        """
        Re-queue messages left in 'sending' after a worker crash or unhandled error.
        Without this, due messages are invisible to process_scheduled_messages forever.
        """
        released = 0
        max_age = float(self.STUCK_SENDING_MAX_AGE_SECONDS)
        for mid, msg in list(self.scheduled_messages.items()):
            if msg.get("status") != "sending":
                continue
            started = msg.get("sending_started_at")
            if isinstance(started, datetime):
                if (now - started).total_seconds() < max_age:
                    continue
            msg["status"] = "scheduled"
            msg.pop("sending_started_at", None)
            msg["last_error"] = "stuck_sending_recovered"
            msg["last_attempt"] = now
            released += 1
            print(f"   [RECOVER] {mid}: was stuck in 'sending' — reset to scheduled for retry")
        if released:
            self._persist_sent_messages()
        return released

    async def process_scheduled_messages(self) -> list[dict]:
        """
        Find all due scheduled messages and mark them as 'sending'.
        The caller is responsible for calling mark_message_sent() or
        mark_message_failed() after the actual send attempt.
        """

        # Don't send messages if smart messaging is disabled
        if not self._is_smart_messaging_enabled():
            print("Smart messaging is disabled, skipping message sending")
            return []

        current_time = datetime.now()
        stuck = self._release_stuck_sending_messages(current_time)
        if stuck:
            print(f"   Recovered {stuck} smart message(s) stuck in 'sending' state")

        messages_to_send = []

        for message_id, message_data in list(self.scheduled_messages.items()):
            if message_data["status"] == "scheduled" and message_data["send_at"] <= current_time:
                # Use edited content if present, otherwise render from template
                content = message_data.get("content")
                if not content:
                    content = self.get_message_content(
                        message_data["message_type"], message_data["language"], message_data["placeholders"]
                    )

                if content:
                    canonical_type = normalize_template_id(message_data["message_type"])
                    messages_to_send.append(
                        {
                            "phone": message_data["customer_phone"],
                            "content": content,
                            "type": canonical_type,
                            "message_id": message_id,
                            "customer_name": message_data.get("placeholders", {}).get("customer_name", "Customer"),
                            "placeholders": dict(message_data.get("placeholders") or {}),
                            "language": message_data.get("language") or "ar",
                        }
                    )

                    # Mark as 'sending' to prevent duplicate processing,
                    # but do NOT mark 'sent' yet — caller does that after
                    # confirming the WhatsApp send succeeded.
                    row = self.scheduled_messages[message_id]
                    row["status"] = "sending"
                    row["sending_started_at"] = current_time
                else:
                    mt = message_data.get("message_type")
                    print(
                        f"⚠️ Smart message {message_id}: no rendered content for template {mt!r} "
                        f"(missing from message_templates.json or empty) — marking failed"
                    )
                    self.scheduled_messages[message_id]["status"] = "failed"
                    self.scheduled_messages[message_id]["last_error"] = "missing_template_content"
                    self.scheduled_messages[message_id]["last_attempt"] = datetime.now()

        return messages_to_send

    def mark_message_dry_run(self, message_id: str) -> None:
        """Mark message as dry-run (would send) – used when ENABLE_SENDING=false or local sandbox."""
        if message_id in self.scheduled_messages:
            self.scheduled_messages[message_id].pop("sending_started_at", None)
            self.scheduled_messages[message_id]["status"] = "would_send"
            self.scheduled_messages[message_id]["sent_at"] = datetime.now()
            msg_data = self.scheduled_messages[message_id]
            canonical_type = normalize_template_id(msg_data.get("message_type", ""))
            content_preview = (
                self.get_message_content(
                    canonical_type, msg_data.get("language", "ar"), msg_data.get("placeholders") or {}
                )
                or ""
            )
            self.sent_messages_log.append(
                {
                    "message_id": message_id,
                    "phone": msg_data.get("customer_phone", ""),
                    "type": canonical_type,
                    "sent_at": datetime.now(),
                    "content": "(dry-run) "
                    + (content_preview[:80] + "..." if len(content_preview) > 80 else content_preview),
                }
            )
            self._persist_sent_messages()
            print(f"   📋 Marked {message_id} as would_send (dry-run)")

    def _log_reminder_sent_analytics(self, message_id: str, msg_data: dict[str, Any]) -> None:
        """Append analytics event when reminder_24h is actually sent."""
        if not msg_data:
            return
        canonical_type = normalize_template_id(msg_data.get("message_type", ""))
        if canonical_type != "reminder_24h":
            return
        metadata = msg_data.get("metadata", {}) if isinstance(msg_data.get("metadata"), dict) else {}
        ph = msg_data.get("placeholders") or {}
        aid = metadata.get("appointment_id") or ph.get("appointment_id")
        phone = msg_data.get("customer_phone")
        d = ph.get("appointment_date")
        t = ph.get("appointment_time")
        ap_at = f"{d} {t}" if d and t else (str(d) if d else None)
        uid = str(phone or "").strip()
        if not uid:
            return
        try:
            from services.analytics_events import analytics

            analytics.log_smart_reminder_sent(
                user_id=uid,
                template_id=canonical_type,
                message_id=message_id,
                appointment_id=aid,
                phone=phone,
                appointment_at=ap_at,
            )
        except Exception as e:
            print(f"⚠️ log_smart_reminder_sent analytics: {e}")

    def mark_message_sent(self, message_id: str) -> None:
        """Mark a single message as successfully sent (called after WhatsApp confirms)."""
        if message_id not in self.scheduled_messages:
            print(
                f"⚠️ mark_message_sent: {message_id!r} not in scheduled_messages "
                f"(server restart drops non-sent rows from disk) — queue state not updated"
            )
            return

        self.scheduled_messages[message_id].pop("sending_started_at", None)
        self.scheduled_messages[message_id]["status"] = "sent"
        self.scheduled_messages[message_id]["sent_at"] = datetime.now()

        msg_data = self.scheduled_messages[message_id]
        metadata = msg_data.get("metadata", {}) if isinstance(msg_data.get("metadata"), dict) else {}
        canonical_type = normalize_template_id(msg_data["message_type"])
        content = self.get_message_content(canonical_type, msg_data["language"], msg_data["placeholders"]) or ""
        self.sent_messages_log.append(
            {
                "message_id": message_id,
                "phone": msg_data["customer_phone"],
                "type": canonical_type,
                "sent_at": datetime.now(),
                "content": content[:100] + "...",
            }
        )

        reference_date = (
            metadata.get("reference_date")
            or msg_data.get("placeholders", {}).get("reference_date")
            or msg_data.get("placeholders", {}).get("appointment_date")
        )
        appointment_id = metadata.get("appointment_id") or msg_data.get("placeholders", {}).get("appointment_id")
        customer_id = metadata.get("customer_id") or msg_data.get("customer_phone")
        campaign_id = metadata.get("campaign_id")

        try:
            if not message_logs_service.was_message_sent(
                customer_id=customer_id,
                template_type=canonical_type,
                reference_date=reference_date,
                appointment_id=appointment_id,
                campaign_id=campaign_id,
            ):
                message_logs_service.log_message(
                    customer_id=customer_id,
                    template_type=canonical_type,
                    appointment_id=appointment_id,
                    campaign_id=campaign_id,
                    reference_date=reference_date,
                    extra={
                        "phone": msg_data.get("customer_phone"),
                        "service_name": msg_data.get("service_name"),
                        "source": metadata.get("source", "scheduler"),
                    },
                )
        except Exception as log_exc:
            print(f"⚠️ Failed to write message log for {message_id}: {log_exc}")

        if canonical_type == "thank_you_message_sent_after_session":
            try:
                from services.post_session_feedback_rating_service import (
                    mark_awaiting_post_session_feedback_after_send,
                )

                mark_awaiting_post_session_feedback_after_send(
                    phone=msg_data.get("customer_phone"),
                    appointment_id=appointment_id,
                    reference_date=str(reference_date) if reference_date is not None else None,
                    smart_message_id=message_id,
                )
            except Exception as psf_e:
                print(f"⚠️ thank_you_message_sent_after_session awaiting flag: {psf_e}")

        self._log_reminder_sent_analytics(message_id, msg_data)
        self._persist_sent_messages()

    def mark_message_failed(self, message_id: str, error: str = "") -> None:
        """Revert a message back to 'scheduled' so it can be retried next cycle."""
        if message_id in self.scheduled_messages:
            msg = self.scheduled_messages[message_id]
            msg.pop("sending_started_at", None)
            msg["status"] = "scheduled"
            msg["last_error"] = error
            msg["last_attempt"] = datetime.now()
            print(f"   [RETRY] {message_id} reverted to 'scheduled' — {error}")
