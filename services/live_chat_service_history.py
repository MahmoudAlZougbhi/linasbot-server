from __future__ import annotations

import asyncio
import datetime
from typing import Any

from google.cloud import firestore

import config
from services.live_chat_contracts import (
    dedupe_messages as contract_dedupe_messages,
)
from services.live_chat_contracts import (
    normalize_conversation_document,
    utc_now,
)
from services.live_chat_service_common import (
    _live_chat_display_name,
)
from utils.utils import (
    get_firestore_db,
)


class LiveChatHistoryMixin:
    """History streaming, filters, and customer-row helpers."""

    def _dedupe_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return contract_dedupe_messages(messages)

    def _is_smart_message(self, message: dict[str, Any]) -> bool:
        metadata = (message or {}).get("metadata", {}) or {}
        return metadata.get("source") == "smart_message"

    def _visible_chat_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Live Chat UI shows all messages including smart messages (scheduled/sent from Smart Messaging).
        Operators need to see the full conversation including automated messages.
        """
        return list(messages or [])

    def _is_cache_fresh(self, cache_time: datetime.datetime | None, ttl_seconds: int | None = None) -> bool:
        if cache_time is None:
            return False
        ttl = ttl_seconds or self.CACHE_TTL
        return (utc_now() - cache_time).total_seconds() < ttl

    def _get_users_collection(self) -> Any:
        db = get_firestore_db()
        if not db:
            return None
        return db.collection("artifacts").document(self.APP_ID).collection("users")

    async def _stream_user_docs(self, users_collection: Any, limit: int | None = None) -> Any:
        if users_collection is None:
            return []
        try:
            q = users_collection.order_by("last_activity", direction=firestore.Query.DESCENDING)
            if limit is not None:
                q = q.limit(limit)
            return await asyncio.to_thread(lambda: list(q.stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS)))
        except Exception:
            try:
                return await asyncio.to_thread(
                    lambda: list(users_collection.stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS))
                )
            except Exception:
                return []

    async def _stream_user_conversations(self, users_collection: Any, user_id: str) -> Any:
        try:
            conversations_collection = users_collection.document(user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            )
            conversations_docs = await asyncio.to_thread(
                lambda: list(conversations_collection.stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS))
            )
            return user_id, conversations_docs
        except Exception as e:
            print(f"⚠️ Error fetching conversations for user {user_id}: {e}")
            return user_id, []

    async def _stream_conversations_for_users(self, users_collection: Any, user_ids: list[str]) -> Any:
        semaphore = asyncio.Semaphore(self.FIRESTORE_FETCH_PARALLELISM)

        async def _bounded_fetch(uid: str) -> Any:
            async with semaphore:
                return await self._stream_user_conversations(users_collection, uid)

        return await asyncio.gather(
            *[_bounded_fetch(uid) for uid in user_ids],
            return_exceptions=True,
        )

    def _history_filter_match(self, dt: datetime.datetime, filter_by: str) -> bool:
        if filter_by == "all":
            return True

        now = utc_now()
        age_hours = (now - dt).total_seconds() / 3600.0

        if filter_by == "today":
            return age_hours <= 24
        if filter_by == "week":
            return age_hours <= 24 * 7
        if filter_by == "month":
            return age_hours <= 24 * 30
        return True

    async def _collect_history_customer_rows(self) -> list[dict[str, Any]]:
        """All WhatsApp chat customers with last activity (no search / time-window / pagination)."""
        users_collection = self._get_users_collection()
        if users_collection is None:
            return []

        users_docs = await self._stream_user_docs(users_collection)
        user_ids = [doc.id for doc in users_docs]
        fetch_results = await self._stream_conversations_for_users(users_collection, user_ids)

        customers: list[dict[str, Any]] = []
        for result in fetch_results:
            if isinstance(result, Exception):
                continue

            user_id, conversations_docs = result

            latest_timestamp = None
            latest_message_text = ""
            latest_customer_info: dict[str, Any] = {}
            total_messages = 0
            conversation_count = 0

            for conv_doc in conversations_docs:
                conversation_count += 1
                conv_data = normalize_conversation_document(
                    conversation_id=conv_doc.id,
                    user_id=user_id,
                    payload=conv_doc.to_dict() or {},
                )
                messages = conv_data.get("messages", [])
                visible_messages = self._visible_chat_messages(messages)
                if not visible_messages:
                    continue

                total_messages += len(visible_messages)
                last_message = visible_messages[-1]
                candidate_ts = self._parse_timestamp(last_message.get("timestamp"))

                if latest_timestamp is None or candidate_ts > latest_timestamp:
                    latest_timestamp = candidate_ts
                    latest_message_text = str(last_message.get("text", ""))
                    latest_customer_info = conv_data.get("customer_info", {}) or {}

            if latest_timestamp is None:
                continue

            user_name = _live_chat_display_name(
                latest_customer_info.get("name"),
                config.user_names.get(str(user_id or "")),
                fallback="",
            )
            phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=latest_customer_info)
            if not user_name and phone_full and phone_full != "Unknown":
                user_name = phone_full
            if not user_name:
                user_name = "Unknown Customer"
            gender = latest_customer_info.get("gender") or config.user_gender.get(user_id, "unknown")

            customers.append(
                {
                    "user_id": user_id,
                    "user_name": user_name,
                    "phone_full": phone_full,
                    "phone_clean": phone_clean,
                    "gender": gender,
                    "last_message": latest_message_text,
                    "last_message_time": latest_timestamp.isoformat(),
                    "message_count": total_messages,
                    "conversation_count": conversation_count,
                    "unread_count": 0,
                }
            )

        return customers

    async def user_chats_mention_any_service_name(
        self,
        user_id: str,
        service_names: list[str],
    ) -> bool:
        """
        True if recent visible chat text contains any of the given service names (substring, lowercase).
        Used for manual lead campaigns when BOC has no appointments to filter on.
        """
        names = [str(n).strip().lower() for n in (service_names or []) if str(n).strip()]
        if not names:
            return True

        db = get_firestore_db()
        if not db:
            return False

        conversations_collection = (
            db.collection("artifacts")
            .document(self.APP_ID)
            .collection("users")
            .document(user_id)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
        )

        conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))

        blob_parts: list[str] = []
        for conv_doc in conversations_docs:
            conv_data = normalize_conversation_document(
                conversation_id=conv_doc.id,
                user_id=user_id,
                payload=conv_doc.to_dict() or {},
            )
            messages = conv_data.get("messages", [])
            visible_messages = self._visible_chat_messages(messages)
            for msg in visible_messages[-60:]:
                blob_parts.append(str(msg.get("text", "")))

        blob = " ".join(blob_parts).lower()
        for n in names:
            if len(n) >= 2 and n in blob:
                return True
        return False

    def _paginate(
        self, items: list[dict[str, Any]], page: int, page_size: int
    ) -> tuple[list[dict[str, Any]], int, int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 1000))
        total_items = len(items)
        total_pages = max(1, (total_items + safe_page_size - 1) // safe_page_size)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return items[start:end], total_items, total_pages
