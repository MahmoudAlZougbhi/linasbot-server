"""AnalyticsEvents event logging methods (LOC split)."""

from __future__ import annotations

import json
import os
from typing import Any


class AnalyticsEventsLogMixin:
    """Append-only event logging helpers."""

    def log_message(
        self,
        source: str,
        msg_type: str,
        user_id: str,
        language: str = "ar",
        sentiment: str | None = None,
        tokens: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
        response_time_ms: float | None = None,
        message_length: int = 0,
        sentiment_detected: bool = False,
    ) -> None:
        """
        Log a message event

        Args:
            source: "user" | "bot" | "human"
            msg_type: "text" | "voice" | "image"
            user_id: User identifier
            language: "ar" | "en" | "fr" | "franco"
            sentiment: "positive" | "neutral" | "negative" when actually computed
            tokens: Number of tokens used (for bot messages)
            cost_usd: Cost in USD (for bot messages)
            model: AI model used (e.g., "gpt-5-mini", "whisper-1")
            response_time_ms: Response time in milliseconds (for bot messages)
            message_length: Length of message in characters
            sentiment_detected: True only when sentiment was computed from a real detector
        """
        payload: dict[str, Any] = {
            "type": "message",
            "source": source,
            "msg_type": msg_type,
            "user_id": user_id,
            "language": language,
            "tokens": tokens,
            "cost_usd": cost_usd,
            "model": model,
            "response_time_ms": response_time_ms,
            "message_length": message_length,
        }
        if sentiment is not None:
            payload["sentiment"] = sentiment
            if sentiment_detected:
                payload["sentiment_detected"] = True
        self._append_event(payload)

    def log_conversation_start(self, user_id: str, conversation_id: str, is_new_user: bool = False) -> None:
        """Log when a new conversation starts"""
        self._append_event(
            {
                "type": "conversation_start",
                "user_id": user_id,
                "conversation_id": conversation_id,
                "is_new_user": is_new_user,
            }
        )

    def log_gender(self, user_id: str, gender: str) -> None:
        """
        Log user gender

        Args:
            gender: "male" | "female" | "unknown"
        """
        self._append_event({"type": "gender", "user_id": user_id, "gender": gender})

    def log_service_request(self, user_id: str, service: str) -> None:
        """Log when user asks about a service"""
        self._append_event({"type": "service_request", "user_id": user_id, "service": service})

    def log_appointment(
        self,
        user_id: str,
        service: str,
        status: str,
        messages_count: int = 0,
        phone: str | None = None,
        appointment_id: Any | None = None,
    ) -> None:
        """
        Log appointment event

        Args:
            status: "requested" | "booked" | "confirmed" | "rescheduled" | "cancelled"
            messages_count: Number of messages in conversation (for conversion tracking)
        """
        aid = None
        if appointment_id is not None:
            try:
                aid = int(appointment_id)
            except (TypeError, ValueError):
                aid = None
        payload: dict[str, Any] = {
            "type": "appointment",
            "user_id": user_id,
            "service": service,
            "status": status,
            "messages_count": messages_count,
        }
        if phone:
            payload["phone"] = str(phone).strip()
        if aid is not None:
            payload["appointment_id"] = aid
        self._append_event(payload)

    def log_smart_reminder_sent(
        self,
        user_id: str,
        template_id: str,
        message_id: str | None = None,
        appointment_id: Any | None = None,
        phone: str | None = None,
        appointment_at: str | None = None,
    ) -> None:
        """Log when a smart template (e.g. reminder_24h) is actually sent to the customer."""
        aid = None
        if appointment_id is not None:
            try:
                aid = int(appointment_id)
            except (TypeError, ValueError):
                aid = None
        self._append_event(
            {
                "type": "smart_reminder_sent",
                "user_id": user_id,
                "template_id": (template_id or "reminder_24h"),
                "message_id": message_id,
                "appointment_id": aid,
                "phone": (str(phone).strip() if phone else None),
                "appointment_at": appointment_at,
            }
        )

    def log_smart_reminder_reply(
        self,
        user_id: str,
        intent: str,
        source_message_id: str | None = None,
        appointment_id: Any | None = None,
        phone: str | None = None,
    ) -> None:
        """
        Log a classified reply to a smart reminder (confirm / postpone / cancel / defer).
        """
        aid = None
        if appointment_id is not None:
            try:
                aid = int(appointment_id)
            except (TypeError, ValueError):
                aid = None
        self._append_event(
            {
                "type": "smart_reminder_reply",
                "user_id": user_id,
                "intent": str(intent or "").strip().lower()[:32],
                "source_message_id": source_message_id,
                "appointment_id": aid,
                "phone": (str(phone).strip() if phone else None),
            }
        )

    def log_feedback(self, user_id: str, feedback_type: str, reason: str | None = None) -> None:
        """
        Log user feedback

        Args:
            feedback_type: "good" | "wrong" | "inappropriate" | "unclear"
            reason: Optional reason for negative feedback
        """
        self._append_event({"type": "feedback", "user_id": user_id, "feedback_type": feedback_type, "reason": reason})

    def log_appointment_pause_cleared(
        self,
        user_id: str,
        appointment_id: Any | None = None,
        phone: str | None = None,
        service: str | None = None,
    ) -> None:
        """
        CRM cleared Paused → Available after update_appointment_date + successful resume API.
        """
        aid = None
        if appointment_id is not None:
            try:
                aid = int(appointment_id)
            except (TypeError, ValueError):
                aid = None
        self._append_event(
            {
                "type": "appointment_pause_cleared",
                "user_id": user_id,
                "appointment_id": aid,
                "phone": (str(phone).strip() if phone else None),
                "service": service,
            }
        )

    def log_session_rating(self, user_id: str, stars: int, conversation_id: str | None = None) -> None:
        """
        Post-conversation star rating (1–5), e.g. after successful booking.

        Args:
            stars: 1–5
            conversation_id: Optional WhatsApp conversation id for dedupe context
        """
        try:
            s = int(stars)
        except (TypeError, ValueError):
            s = 0
        s = max(1, min(5, s))
        self._append_event(
            {
                "type": "session_rating",
                "user_id": user_id,
                "stars": s,
                "conversation_id": conversation_id,
            }
        )

    def log_post_session_feedback_rating(
        self,
        user_id: str,
        stars: int,
        conversation_id: str | None = None,
        appointment_id: Any | None = None,
        reference_date: str | None = None,
        raw_reply: str | None = None,
        smart_message_id: str | None = None,
    ) -> None:
        """Star rating (1–5) after Post Session Feedback WhatsApp template (smart messaging)."""
        try:
            s = int(stars)
        except (TypeError, ValueError):
            s = 0
        s = max(1, min(5, s))
        self._append_event(
            {
                "type": "post_session_feedback_rating",
                "user_id": user_id,
                "stars": s,
                "conversation_id": conversation_id,
                "appointment_id": appointment_id,
                "reference_date": reference_date,
                "raw_reply": (raw_reply or "")[:500] if raw_reply else None,
                "smart_message_id": smart_message_id,
            }
        )

    def get_post_session_feedback_ratings(self, limit: int = 200) -> list[dict[str, Any]]:
        """Recent post_session_feedback_rating events (newest first)."""
        try:
            lim = max(1, min(2000, int(limit)))
        except (TypeError, ValueError):
            lim = 200
        if not os.path.exists(self.events_file):
            return []
        rows: list[dict[str, Any]] = []
        try:
            with open(self.events_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "post_session_feedback_rating":
                        rows.append(obj)
        except OSError:
            return []
        rows.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
        return rows[:lim]

    def log_escalation(self, user_id: str, escalation_type: str, reason: str | None = None) -> None:
        """
        Log escalation event

        Args:
            escalation_type: "human_handover" | "complaint" | "technical_issue" | "bot_failure"
            reason: Optional reason for escalation
        """
        self._append_event(
            {"type": "escalation", "user_id": user_id, "escalation_type": escalation_type, "reason": reason}
        )

    def log_topic(self, user_id: str, topic: str, category: str = "general") -> None:
        """Log trending topic/question"""
        self._append_event({"type": "topic", "user_id": user_id, "topic": topic, "category": category})
