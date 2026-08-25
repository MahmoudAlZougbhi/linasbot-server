from __future__ import annotations

import asyncio
from typing import Any

import config
from services.live_chat_contracts import (
    normalize_conversation_document,
    parse_timestamp_utc,
    utc_now,
)
from services.live_chat_service_common import (
    _live_chat_display_name,
)
from utils.utils import (
    get_firestore_db,
)


class LiveChatHistoryApiMixin:
    """History API reads and waiting-queue listing."""

    _conversations_cache: Any
    _conversations_cache_time: Any
    _queue_cache: Any
    _queue_cache_time: Any
    _unified_chats_cache: Any
    _unified_chats_cache_time: Any
    _unified_chats_cache_has_more: Any
    _unified_chats_cache_total: Any
    _unified_chats_cache_next_cursor: Any
    _unified_chats_cache_page_size: Any
    _index_counters_cache: Any
    _index_counters_cache_time: Any
    _index_write_paused_until: Any
    _phone_mapping_cache_time: Any
    _room_to_phone_cache: Any
    _phone_to_room_cache: Any

    FIRESTORE_QUERY_TIMEOUT_SECONDS: Any
    STATE_WAITING_OPERATOR: Any
    _collect_history_customer_rows: Any
    _get_users_collection: Any
    _history_filter_match: Any
    _index_collection: Any
    _index_recency_query: Any
    _is_cache_fresh: Any
    _normalize_conversation_state: Any
    _paginate: Any
    _parse_timestamp: Any
    _visible_chat_messages: Any

    async def get_history_customers(
        self,
        search: str = "",
        filter_by: str = "all",
        page: int = 1,
        page_size: int = 200,
    ) -> dict[str, Any]:
        """Canonical customer list for chat history."""
        try:
            users_collection = self._get_users_collection()
            if users_collection is None:
                return {"success": False, "error": "Firestore not initialized"}

            customers = await self._collect_history_customer_rows()

            search_value = (search or "").strip().lower()
            if search_value:
                filtered_customers = []
                for customer in customers:
                    if (
                        search_value in str(customer.get("user_name", "")).lower()
                        or search_value in str(customer.get("user_id", "")).lower()
                        or search_value in str(customer.get("phone_full", "")).lower()
                        or search_value in str(customer.get("phone_clean", "")).lower()
                        or search_value in str(customer.get("last_message", "")).lower()
                    ):
                        filtered_customers.append(customer)
                customers = filtered_customers

            customers = [
                customer
                for customer in customers
                if self._history_filter_match(self._parse_timestamp(customer.get("last_message_time")), filter_by)
            ]

            customers.sort(key=lambda item: item.get("last_message_time", ""), reverse=True)
            paged_customers, total_customers, total_pages = self._paginate(customers, page, page_size)

            return {
                "success": True,
                "customers": paged_customers,
                "total_customers": total_customers,
                "page": max(1, int(page)),
                "page_size": max(1, min(int(page_size), 1000)),
                "total_pages": total_pages,
            }
        except Exception as e:
            print(f"❌ Error getting history customers: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def get_history_conversations(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 200,
        status: str = "all",
        search: str = "",
    ) -> dict[str, Any]:
        """Canonical conversation list for a single user."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conversations_collection = (
                db.collection("artifacts")
                .document(app_id)
                .collection("users")
                .document(user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            )

            conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))

            conversations: list[dict[str, Any]] = []
            total_messages = 0
            for conv_doc in conversations_docs:
                conv_data = normalize_conversation_document(
                    conversation_id=conv_doc.id,
                    user_id=user_id,
                    payload=conv_doc.to_dict() or {},
                )
                messages = conv_data.get("messages", [])
                visible_messages = self._visible_chat_messages(messages)
                message_count = len(visible_messages)
                total_messages += message_count

                last_timestamp = self._parse_timestamp(conv_data.get("timestamp"))
                last_message = None
                if visible_messages:
                    raw_last = visible_messages[-1]
                    last_timestamp = self._parse_timestamp(raw_last.get("timestamp"))
                    last_message = {
                        "role": raw_last.get("role"),
                        "text": raw_last.get("text", ""),
                        "timestamp": last_timestamp.isoformat(),
                        "type": raw_last.get("type", "text"),
                    }

                conversations.append(
                    {
                        "id": conv_doc.id,
                        "message_count": message_count,
                        "last_message": last_message,
                        "timestamp": last_timestamp.isoformat(),
                        "user_id": conv_data.get("user_id", user_id),
                        "sentiment": conv_data.get("sentiment", "neutral"),
                        "human_takeover_active": conv_data.get("human_takeover_active", False),
                        "status": conv_data.get("status", "active"),
                    }
                )

            if status and status != "all":
                conversations = [conv for conv in conversations if conv.get("status") == status]

            search_value = (search or "").strip().lower()
            if search_value:
                conversations = [
                    conv
                    for conv in conversations
                    if search_value in str(conv.get("id", "")).lower()
                    or search_value in str(conv.get("status", "")).lower()
                    or search_value in str((conv.get("last_message") or {}).get("text", "")).lower()
                ]

            conversations.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
            paged_conversations, total_conversations, total_pages = self._paginate(conversations, page, page_size)

            return {
                "success": True,
                "conversations": paged_conversations,
                "user_id": user_id,
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "page": max(1, int(page)),
                "page_size": max(1, min(int(page_size), 1000)),
                "total_pages": total_pages,
            }
        except Exception as e:
            print(f"❌ Error getting history conversations for ...{str(user_id)[-4:]}: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def get_history_messages(
        self,
        user_id: str,
        conversation_id: str,
        page: int = 1,
        page_size: int = 1000,
        search: str = "",
        sort: str = "asc",
    ) -> dict[str, Any]:
        """Canonical paginated message history for one conversation."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized", "messages": []}

            app_id = "linas-ai-bot-backend"
            conv_ref = (
                db.collection("artifacts")
                .document(app_id)
                .collection("users")
                .document(user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )

            conv_doc = await asyncio.to_thread(conv_ref.get)
            if not conv_doc.exists:
                return {"success": False, "error": "Conversation not found", "messages": []}

            conv_data = conv_doc.to_dict() or {}
            conv_data = normalize_conversation_document(
                conversation_id=conv_doc.id,
                user_id=user_id,
                payload=conv_data,
            )
            messages = conv_data.get("messages", [])
            visible_messages = self._visible_chat_messages(messages)
            normalized_messages = []
            for msg in visible_messages:
                normalized_messages.append(
                    {
                        **msg,
                        "timestamp": self._parse_timestamp(msg.get("timestamp")).isoformat(),
                    }
                )

            search_value = (search or "").strip().lower()
            if search_value:
                normalized_messages = [
                    msg for msg in normalized_messages if search_value in str(msg.get("text", "")).lower()
                ]

            reverse_sort = str(sort).lower() == "desc"
            normalized_messages.sort(key=lambda item: item.get("timestamp", ""), reverse=reverse_sort)
            safe_page = max(1, int(page))
            safe_page_size = max(1, min(int(page_size), 1000))
            total_messages = len(normalized_messages)
            total_pages = max(1, (total_messages + safe_page_size - 1) // safe_page_size)

            # Backward-compatible default: when UI requests page 1 in ascending order,
            # return the latest chunk so recent messages are always visible.
            if (not reverse_sort) and safe_page == 1 and total_messages > safe_page_size:
                paged_messages = normalized_messages[-safe_page_size:]
            else:
                paged_messages, _, _ = self._paginate(normalized_messages, safe_page, safe_page_size)

            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": paged_messages,
                "total_messages": total_messages,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": total_pages,
                "returned_messages": len(paged_messages),
            }
        except Exception as e:
            print(f"❌ Error getting history messages for {conversation_id}: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e), "messages": []}

    async def get_client_conversations(self, user_id: str) -> Any:
        """
        Get all conversations for a specific client (for expanded view)
        """
        try:
            db = get_firestore_db()
            if not db:
                return []

            app_id = "linas-ai-bot-backend"
            conversations_collection = (
                db.collection("artifacts")
                .document(app_id)
                .collection("users")
                .document(user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            )

            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))
            conversations = []

            for conv_doc in conversations_docs:
                conv_data = normalize_conversation_document(
                    conversation_id=conv_doc.id,
                    user_id=user_id,
                    payload=conv_doc.to_dict() or {},
                )
                messages = conv_data.get("messages", [])
                visible_messages = self._visible_chat_messages(messages)

                if not visible_messages:
                    continue

                last_message = visible_messages[-1]
                last_message_time = self._parse_timestamp(last_message.get("timestamp"))

                conversations.append(
                    {
                        "conversation_id": conv_doc.id,
                        "message_count": len(visible_messages),
                        "last_activity": last_message_time.isoformat(),
                        "status": conv_data.get("status", "active"),
                        "sentiment": conv_data.get("sentiment", "neutral"),
                        "human_takeover_active": conv_data.get("human_takeover_active", False),
                        "operator_id": conv_data.get("operator_id"),
                    }
                )

            conversations.sort(key=lambda x: x["last_activity"], reverse=True)
            return conversations

        except Exception as e:
            print(f"❌ Error getting client conversations: {e}")
            return []

    async def get_waiting_queue(self) -> Any:
        """
        Get conversations waiting for human intervention
        Queries live_chat_index for conversations_state == waiting_for_operator
        """
        try:
            current_time = utc_now()
            # Use short cache to keep UI responsive while staying near real-time.
            if self._queue_cache is not None and self._is_cache_fresh(self._queue_cache_time):
                return self._queue_cache

            db = get_firestore_db()
            if not db:
                return []

            index_coll = self._index_collection(db)
            docs = await asyncio.to_thread(
                lambda: list(
                    self._index_recency_query(index_coll)
                    .limit(300)
                    .stream(
                        timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                        retry=None,
                    )
                )
            )

            if not docs:
                print(
                    "[live_chat:waiting_queue] index empty — refusing source full-scan; "
                    "run live chat index backfill/rebuild"
                )
                self._queue_cache = []
                self._queue_cache_time = current_time
                return []

            waiting_queue = []

            for doc in docs:
                data = doc.to_dict() or {}
                data["conversation_id"] = doc.id
                # Explicit True only: fallback query uses conversation_state and can return rows missing
                # human_takeover_active (stale index) — those must not appear as waiting after release.
                if data.get("human_takeover_active") is not True:
                    continue
                # Stale index rows can still have hta=True; honor release cooldown if present on index
                try:
                    _raw_sup = data.get("post_release_escalation_suppressed_until")
                    if _raw_sup is not None:
                        _sup = parse_timestamp_utc(_raw_sup)
                        if _sup and _sup > utc_now():
                            continue
                except Exception:
                    pass
                state = self._normalize_conversation_state(data)
                if state != self.STATE_WAITING_OPERATOR:
                    continue

                last_at = data.get("last_message_at") or data.get("last_updated") or current_time
                if isinstance(last_at, str):
                    try:
                        last_at = self._parse_timestamp(last_at)
                    except Exception:
                        last_at = current_time

                wait_time_seconds = max(0, int((current_time - last_at).total_seconds()))
                customer_info = data.get("customer_info") or {}
                user_id = data.get("user_id")
                user_name = _live_chat_display_name(
                    customer_info.get("name"),
                    config.user_names.get(str(user_id or "")),
                )
                phone_full = data.get("user_phone") or "Unknown"
                phone_clean = data.get("phone_clean") or "Unknown"
                language = data.get("language") or config.user_data_whatsapp.get(str(user_id or ""), {}).get(
                    "user_preferred_lang", "ar"
                )
                sentiment = data.get("sentiment", "neutral")
                priority = 1 if sentiment == "negative" or wait_time_seconds > 300 else 2

                queue_item = {
                    "conversation_id": data.get("conversation_id"),
                    "user_id": user_id,
                    "user_name": user_name,
                    "user_phone": phone_full,
                    "phone_clean": phone_clean,
                    "language": language,
                    "reason": data.get("escalation_reason", "user_request"),
                    "wait_time_seconds": wait_time_seconds,
                    "sentiment": sentiment,
                    "message_count": data.get("message_count", 0),
                    "unread_count": data.get("unread_count", 0),
                    "priority": priority,
                    "last_message": data.get("last_message_text", ""),
                    "is_new_customer": data.get("is_new_customer", False),
                }

                waiting_queue.append(queue_item)

            # Index rows that do not normalize to waiting are not scanned from source.
            if not waiting_queue:
                print("[live_chat:waiting_queue] index docs present but none waiting — refusing source full-scan")

            # Sort by priority (1=high, 2=normal) then by wait time (longest first)
            waiting_queue.sort(key=lambda x: (x["priority"], -x["wait_time_seconds"]))

            # Update cache
            self._queue_cache = waiting_queue
            self._queue_cache_time = current_time

            print(f"📊 Waiting queue: {len(waiting_queue)} conversations")

            return waiting_queue

        except Exception as e:
            print(f"❌ Error getting waiting queue: {e}")
            import traceback

            traceback.print_exc()
            return []

    async def _fallback_waiting_queue_from_source(self, limit: int = 500) -> list:
        """Removed from request paths. Use scripts/backfill_live_chat_index.py."""
        raise RuntimeError(
            "Legacy Live Chat waiting-queue source scan is disabled; "
            "run scripts/backfill_live_chat_index.py or POST /api/live-chat/rebuild-index"
        )
