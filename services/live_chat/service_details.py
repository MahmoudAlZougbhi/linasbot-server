"""Active Live Chat operator details mixin imported by service.py.

Residual scrub skips folding this into service.py — Live Chat already splits
by mixin (history, operator, phone, …) and a fold would be a behavior-risk
move, not a dead-island delete.
"""

from __future__ import annotations

from typing import Any


class LiveChatDetailsMixin:
    """Conversation details and history for Live Chat."""

    ENABLE_INDEX_BACKFILL_ON_READ: Any
    INDEX_READ_TIMEOUT_SECONDS: Any
    _conversation_state_to_status: Any
    _normalize_conversation_state: Any
    _format_single_message: Any
    _get_doc_with_timeout: Any
    _index_collection: Any
    _parse_timestamp: Any
    _refresh_index_for_conversation: Any
    _should_schedule_read_path_refresh: Any
    _visible_chat_messages: Any
    thread_visible_to_tenant: Any

    async def get_conversation_details(
        self,
        user_id: str,
        conversation_id: str,
        max_messages: int = 100,
        days: int = 0,
        before: str | None = None,
        day_window: int = 0,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Get detailed conversation history.

        Args:
            user_id: The user's ID
            conversation_id: The conversation document ID
            max_messages: Max messages to return (default 100)
            days: If > 0, return only messages from last N days (default 0 = no day limit)
            before: If provided (ISO timestamp), return only messages older than this (for Load More)
            day_window: If before is set and > 0, return only messages in (before - day_window days, before]
        """
        try:
            from services.live_chat.tenant import normalize_live_chat_tenant_id
            from services.persistence.chat_store import get_thread, list_messages

            workspace = normalize_live_chat_tenant_id(tenant_id)
            if not workspace:
                return {"success": False, "error": "Conversation not found"}
            thread = get_thread(workspace, conversation_id)
            if thread is None:
                return {"success": False, "error": "Conversation not found"}
            rows = list_messages(workspace, conversation_id, limit=max_messages, before=before)
            messages = []
            for row in reversed(rows):
                meta = {}
                try:
                    import json

                    meta = json.loads(row.get("metadata_json") or "{}")
                except Exception:
                    meta = {}
                messages.append(
                    self._format_single_message(
                        {
                            "message_id": row["message_id"],
                            "role": row["role"],
                            "text": row["body"],
                            "timestamp": row["sent_at"],
                            "metadata": meta if isinstance(meta, dict) else {},
                        }
                    )
                )
            total = int(thread.get("message_count") or len(messages))
            state = str(thread.get("conversation_state") or "")
            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": messages,
                "total_messages": total,
                "returned_messages": len(messages),
                "has_more": total > len(messages),
                "sentiment": "neutral",
                "status": self._conversation_state_to_status(state or "bot_active"),
            }
        except Exception as e:
            print(f"Error getting conversation details: {e}")
            return {"success": False, "error": str(e)}
