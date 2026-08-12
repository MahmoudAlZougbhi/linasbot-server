"""Query Firestore for sent smart messages (LOC split)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from services.smart_messaging_deliver import message_type_names


async def get_sent_smart_messages_from_firestore(
    message_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 200,
) -> list[dict]:
    """
    Query Firestore for sent smart messages by scanning conversations.

    Args:
        message_type: Filter by message type (e.g., "sent_17_days_after_last_session_new")
        start_date: Filter messages sent after this date
        end_date: Filter messages sent before this date
        limit: Maximum number of messages to return

    Returns:
        List of sent message dicts with customer info
    """
    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if not db:
        return []

    app_id = "linas-ai-bot-backend"
    users_collection = db.collection("artifacts").document(app_id).collection("users")

    sent_messages: list[Any] = []

    try:
        # Get all users
        users_docs = await asyncio.to_thread(lambda: list(users_collection.stream()))

        for user_doc in users_docs:
            try:
                user_id = user_doc.id
                user_data = user_doc.to_dict() or {}

                def _fetch_conversations(uid: str = str(user_id)) -> list[Any]:
                    return list(users_collection.document(uid).collection("conversations").stream())

                conversations_docs = await asyncio.to_thread(_fetch_conversations)

                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict() or {}
                    messages = conv_data.get("messages", [])
                    customer_info = conv_data.get("customer_info", {})

                    for msg in messages:
                        metadata = msg.get("metadata", {})

                        # Filter by source - only smart messages
                        if metadata.get("source") != "smart_message":
                            continue

                        # Filter by type if specified
                        if message_type and metadata.get("type") != message_type:
                            continue

                        # Only AI messages (sent by bot)
                        if msg.get("role") != "ai":
                            continue

                        # Parse timestamp
                        timestamp = msg.get("timestamp")
                        msg_datetime = None

                        if hasattr(timestamp, "isoformat"):
                            # Firestore timestamp object
                            msg_datetime = timestamp
                        elif isinstance(timestamp, str):
                            try:
                                msg_datetime = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            except Exception:
                                continue
                        else:
                            continue

                        # Apply date range filter
                        if start_date:
                            # Handle timezone-aware vs naive datetime comparison
                            start_compare = start_date
                            msg_compare = msg_datetime
                            if hasattr(msg_datetime, "tzinfo") and msg_datetime.tzinfo is not None:
                                if start_date.tzinfo is None:
                                    msg_compare = msg_datetime.replace(tzinfo=None)
                            if msg_compare < start_compare:
                                continue

                        if end_date:
                            end_compare = end_date
                            msg_compare = msg_datetime
                            if hasattr(msg_datetime, "tzinfo") and msg_datetime.tzinfo is not None:
                                if end_date.tzinfo is None:
                                    msg_compare = msg_datetime.replace(tzinfo=None)
                            if msg_compare > end_compare:
                                continue

                        # Build message entry matching API format
                        msg_type = metadata.get("type", "smart_message")
                        text_content = msg.get("text", "")

                        sent_messages.append(
                            {
                                "message_id": metadata.get(
                                    "message_id", f"firestore_{conv_doc.id}_{len(sent_messages)}"
                                ),
                                "customer_phone": customer_info.get("phone_full") or user_data.get("phone_full", ""),
                                "customer_name": customer_info.get("name") or user_data.get("name", "Unknown"),
                                "message_type": msg_type,
                                "language": msg.get("language", "ar"),
                                "status": "sent",
                                "reason": message_type_names.get(msg_type, msg_type),
                                "sent_at": msg_datetime.isoformat()
                                if hasattr(msg_datetime, "isoformat")
                                else str(msg_datetime),
                                "content_preview": text_content[:100] + "..."
                                if len(text_content) > 100
                                else text_content,
                                "full_content": text_content,
                                "template_data": {},
                                "source": "firestore",
                            }
                        )

            except Exception as e:
                print(f"Error processing user {user_doc.id}: {e}")
                continue

        # Sort by sent_at descending (newest first)
        sent_messages.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
        return sent_messages[:limit]

    except Exception as e:
        print(f"Error querying Firestore for sent messages: {e}")
        import traceback

        traceback.print_exc()
        return []
