from __future__ import annotations

# Live Conversation Monitoring Service
# Implements requirement #5 from project specifications
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any


class ConversationStatus(Enum):
    BOT_HANDLING = "bot"
    HUMAN_HANDLING = "human"
    WAITING_HUMAN = "waiting_human"
    RESOLVED = "resolved"


class LiveMonitoringService:
    """
    Handles live conversation monitoring and human takeover
    - Real-time conversation tracking
    - Human operator takeover
    - Conversation routing
    - Status management
    """

    def __init__(self) -> None:
        self.active_conversations: dict[str, dict[str, Any]] = {}
        self.conversation_history: dict[str, list[dict[str, Any]]] = {}
        self.operator_assignments: dict[str, list[str]] = {}
        self.waiting_queue: list[str] = []
        self.websocket_connections: list[Any] = []
        self.takeover_callbacks: dict[str, Callable[..., Any]] = {}

    def start_conversation(self, user_id: str, user_data: dict) -> str:
        """Start tracking a new conversation"""

        conversation_id = f"conv_{user_id}_{datetime.now().timestamp()}"

        self.active_conversations[conversation_id] = {
            "id": conversation_id,
            "user_id": user_id,
            "user_name": user_data.get("name", "Unknown"),
            "user_phone": user_data.get("phone", user_id),
            "user_gender": user_data.get("gender", "unknown"),
            "language": user_data.get("language", "ar"),
            "status": ConversationStatus.BOT_HANDLING,
            "started_at": datetime.now(),
            "last_activity": datetime.now(),
            "message_count": 0,
            "operator_id": None,
            "tags": [],
            "sentiment": "neutral",
        }

        # Initialize history
        self.conversation_history[conversation_id] = []

        return conversation_id

    def add_message(self, conversation_id: str, message: dict, is_user: bool = True) -> Any:
        """Add a message to conversation history"""

        if conversation_id not in self.active_conversations:
            return False

        # Update conversation
        self.active_conversations[conversation_id]["last_activity"] = datetime.now()
        self.active_conversations[conversation_id]["message_count"] += 1

        # Detect sentiment/urgency
        if is_user:
            sentiment = self._detect_sentiment(message.get("content", ""))
            self.active_conversations[conversation_id]["sentiment"] = sentiment

            # Check for urgent keywords
            if self._is_urgent(message.get("content", "")):
                self.request_human_takeover(conversation_id, "urgent_detected")

        # Add to history
        message_entry = {
            "timestamp": datetime.now(),
            "is_user": is_user,
            "content": message.get("content", ""),
            "type": message.get("type", "text"),
            "metadata": message.get("metadata", {}),
            "handled_by": self.active_conversations[conversation_id]["status"].value,
        }

        self.conversation_history[conversation_id].append(message_entry)

        # Notify websocket connections
        self._broadcast_update(conversation_id, "new_message", message_entry)

        return True

    def request_human_takeover(self, conversation_id: str, reason: str = "user_request") -> bool:
        """Request human operator takeover"""

        if conversation_id not in self.active_conversations:
            return False

        conv = self.active_conversations[conversation_id]

        # Update status
        conv["status"] = ConversationStatus.WAITING_HUMAN
        conv["takeover_reason"] = reason
        conv["takeover_requested_at"] = datetime.now()

        # Add to waiting queue
        if conversation_id not in self.waiting_queue:
            self.waiting_queue.append(conversation_id)

        # Notify operators
        self._broadcast_update(
            conversation_id,
            "takeover_requested",
            {"reason": reason, "user": conv["user_name"], "language": conv["language"], "sentiment": conv["sentiment"]},
        )

        return True

    def assign_operator(self, conversation_id: str, operator_id: str) -> bool:
        """Assign conversation to human operator"""

        if conversation_id not in self.active_conversations:
            return False

        conv = self.active_conversations[conversation_id]

        # Update assignment
        conv["status"] = ConversationStatus.HUMAN_HANDLING
        conv["operator_id"] = operator_id
        conv["takeover_at"] = datetime.now()

        # Remove from queue
        if conversation_id in self.waiting_queue:
            self.waiting_queue.remove(conversation_id)

        # Track operator assignment
        if operator_id not in self.operator_assignments:
            self.operator_assignments[operator_id] = []
        self.operator_assignments[operator_id].append(conversation_id)

        # Notify
        self._broadcast_update(conversation_id, "operator_assigned", {"operator_id": operator_id})

        return True

    def release_to_bot(self, conversation_id: str, operator_id: str) -> bool:
        """Release conversation back to bot"""

        if conversation_id not in self.active_conversations:
            return False

        conv = self.active_conversations[conversation_id]

        # Verify operator
        if conv["operator_id"] != operator_id:
            return False

        # Update status
        conv["status"] = ConversationStatus.BOT_HANDLING
        conv["operator_id"] = None
        conv["released_at"] = datetime.now()

        # Remove from operator assignments
        if operator_id in self.operator_assignments:
            if conversation_id in self.operator_assignments[operator_id]:
                self.operator_assignments[operator_id].remove(conversation_id)

        # Notify
        self._broadcast_update(conversation_id, "released_to_bot", {})

        return True

    def get_waiting_queue(self) -> list[dict]:
        """Get conversations waiting for human operator"""

        queue = []
        for conv_id in self.waiting_queue:
            if conv_id in self.active_conversations:
                conv = self.active_conversations[conv_id]
                wait_time = (datetime.now() - conv["takeover_requested_at"]).seconds

                queue.append(
                    {
                        "conversation_id": conv_id,
                        "user_name": conv["user_name"],
                        "user_phone": conv["user_phone"],
                        "language": conv["language"],
                        "reason": conv.get("takeover_reason", "unknown"),
                        "wait_time_seconds": wait_time,
                        "sentiment": conv["sentiment"],
                        "message_count": conv["message_count"],
                    }
                )

        # Sort by wait time (longest first)
        queue.sort(key=lambda x: x["wait_time_seconds"], reverse=True)

        return queue

    def get_active_conversations(self, status_filter: ConversationStatus | None = None) -> list[dict]:
        """Get list of active conversations"""

        conversations = []

        for conv_id, conv in self.active_conversations.items():
            if status_filter and conv["status"] != status_filter:
                continue

            # Get last message
            last_message = None
            if conv_id in self.conversation_history and self.conversation_history[conv_id]:
                last_message = self.conversation_history[conv_id][-1]

            conversations.append(
                {
                    "conversation_id": conv_id,
                    "user_name": conv["user_name"],
                    "user_phone": conv["user_phone"],
                    "status": conv["status"].value,
                    "language": conv["language"],
                    "message_count": conv["message_count"],
                    "last_activity": conv["last_activity"].isoformat(),
                    "duration_seconds": (datetime.now() - conv["started_at"]).seconds,
                    "operator_id": conv["operator_id"],
                    "sentiment": conv["sentiment"],
                    "last_message": last_message,
                }
            )

        # Sort by last activity (most recent first)
        conversations.sort(key=lambda x: x["last_activity"], reverse=True)

        return conversations

    def get_conversation_details(self, conversation_id: str) -> dict | None:
        """Get full conversation details with history"""

        if conversation_id not in self.active_conversations:
            return None

        conv = self.active_conversations[conversation_id]
        history = self.conversation_history.get(conversation_id, [])

        # Format history
        formatted_history = []
        for msg in history:
            formatted_history.append(
                {
                    "timestamp": msg["timestamp"].isoformat(),
                    "is_user": msg["is_user"],
                    "content": msg["content"],
                    "type": msg["type"],
                    "handled_by": msg["handled_by"],
                }
            )

        return {
            "conversation": {
                "id": conversation_id,
                "user_name": conv["user_name"],
                "user_phone": conv["user_phone"],
                "user_gender": conv["user_gender"],
                "language": conv["language"],
                "status": conv["status"].value,
                "started_at": conv["started_at"].isoformat(),
                "last_activity": conv["last_activity"].isoformat(),
                "message_count": conv["message_count"],
                "operator_id": conv["operator_id"],
                "sentiment": conv["sentiment"],
                "tags": conv["tags"],
            },
            "history": formatted_history,
        }

    def get_operator_stats(self, operator_id: str) -> dict:
        """Get statistics for an operator"""

        assigned_conversations: list[str] = self.operator_assignments.get(operator_id, [])

        # Count handled conversations
        total_handled = 0
        total_messages = 0
        avg_handling_time = 0

        for conv_id in assigned_conversations:
            if conv_id in self.active_conversations:
                total_handled += 1
                total_messages += self.active_conversations[conv_id]["message_count"]

        return {
            "operator_id": operator_id,
            "active_conversations": len(assigned_conversations),
            "total_handled_today": total_handled,
            "total_messages": total_messages,
            "avg_handling_time_seconds": avg_handling_time,
        }

    def _detect_sentiment(self, message: str) -> str:
        """Detect message sentiment"""

        message_lower = message.lower()

        # Negative indicators
        negative_words = [
            "غاضب",
            "زعلان",
            "مشكلة",
            "سيء",
            "فاشل",
            "مستاء",
            "angry",
            "upset",
            "problem",
            "bad",
            "terrible",
            "disappointed",
            "fâché",
            "problème",
            "mauvais",
            "terrible",
        ]

        # Positive indicators
        positive_words = [
            "شكرا",
            "ممتاز",
            "رائع",
            "سعيد",
            "جميل",
            "thanks",
            "excellent",
            "great",
            "happy",
            "wonderful",
            "merci",
            "excellent",
            "super",
            "heureux",
        ]

        # Check sentiment
        for word in negative_words:
            if word in message_lower:
                return "negative"

        for word in positive_words:
            if word in message_lower:
                return "positive"

        return "neutral"

    def _is_urgent(self, message: str) -> bool:
        """Check if message contains urgent keywords"""

        urgent_words = [
            "عاجل",
            "ضروري",
            "الآن",
            "فورا",
            "مستعجل",
            "طوارئ",
            "urgent",
            "emergency",
            "now",
            "immediately",
            "asap",
            "urgent",
            "urgence",
            "maintenant",
            "immédiatement",
        ]

        message_lower = message.lower()
        return any(word in message_lower for word in urgent_words)

    def _broadcast_update(self, conversation_id: str, event_type: str, data: dict) -> None:
        """Broadcast update to all websocket connections"""

        _update = {
            "event": event_type,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        # In production, this would send to actual websocket connections
        # For now, we'll store for retrieval
        for _connection in self.websocket_connections:
            # Send update to connection
            pass

    def register_takeover_callback(self, conversation_id: str, callback: Callable) -> None:
        """Register callback for when conversation is taken over"""
        self.takeover_callbacks[conversation_id] = callback

    def end_conversation(self, conversation_id: str) -> bool:
        """End and archive a conversation"""

        if conversation_id not in self.active_conversations:
            return False

        conv = self.active_conversations[conversation_id]
        conv["status"] = ConversationStatus.RESOLVED
        conv["ended_at"] = datetime.now()

        # Archive conversation (in production, save to database)
        # For now, just remove from active
        del self.active_conversations[conversation_id]

        # Clean up
        if conversation_id in self.waiting_queue:
            self.waiting_queue.remove(conversation_id)

        return True


# Global instance
live_monitoring = LiveMonitoringService()
