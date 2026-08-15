from __future__ import annotations

from typing import Any

from google.cloud import firestore

import config
from services.live_chat_channel import (
    coerce_live_chat_user_id,
    live_chat_channel_matches,
    normalize_live_chat_channel,
    resolve_live_chat_channel,
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


class LiveChatUnifiedMixin:
    """Unified chat list queries and fallback scans."""

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
    _index_counters_cache_time: Any
    _index_write_paused_until: Any
    _phone_mapping_cache_time: Any
    _room_to_phone_cache: Any
    _phone_to_room_cache: Any

    FIRESTORE_QUERY_TIMEOUT_SECONDS: Any
    SEARCH_WIDEN_MAX_DOCS: Any
    STATE_ASSIGNED: Any
    STATE_BOT_ACTIVE: Any
    STATE_WAITING_OPERATOR: Any
    UNIFIED_CACHE_TTL: Any
    _cached_unified_response: Any
    _compute_index_counters: Any
    _empty_counters: Any
    _empty_unified_response: Any
    _filter_conversations: Any
    _get_users_collection: Any
    _index_collection: Any
    _index_counters_cache: Any
    _is_cache_fresh: Any
    _is_live_window: Any
    _normalize_conversation_state: Any
    _parse_timestamp: Any
    _persist_unified_cache_to_disk: Any
    _resolve_user_phone: Any
    _run_blocking_with_timeout: Any
    _state_filter_values: Any
    _stream_conversations_for_users: Any
    _stream_user_docs: Any
    _to_frontend_chat_format: Any
    _visible_chat_messages: Any

    async def _legacy_active_scan_for_fallback(
        self, search: str | None = None, user_limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Lightweight scan of conversations (legacy path) used only as a safety fallback when index is empty."""
        users_collection = self._get_users_collection()
        if users_collection is None:
            return []

        try:
            users_docs = await self._stream_user_docs(users_collection, limit=user_limit)
            user_ids = [doc.id for doc in users_docs]
            conversation_results = await self._stream_conversations_for_users(users_collection, user_ids)

            conversations: list[dict[str, Any]] = []
            current_time = utc_now()
            for result in conversation_results:
                if isinstance(result, Exception):
                    continue
                user_id, conv_docs = result
                for conv_doc in conv_docs:
                    conv_data = normalize_conversation_document(
                        conversation_id=conv_doc.id,
                        user_id=user_id,
                        payload=conv_doc.to_dict() or {},
                    )
                    state = self._normalize_conversation_state(conv_data)
                    messages = self._visible_chat_messages(conv_data.get("messages", []) or [])
                    last_msg = messages[-1] if messages else {}
                    last_at = (
                        self._parse_timestamp(last_msg.get("timestamp"))
                        if last_msg
                        else conv_data.get("last_updated") or current_time
                    )
                    if isinstance(last_at, str):
                        try:
                            last_at = self._parse_timestamp(last_at)
                        except Exception:
                            last_at = current_time

                    if state not in {self.STATE_BOT_ACTIVE, self.STATE_WAITING_OPERATOR, self.STATE_ASSIGNED}:
                        continue
                    if not last_at or not self._is_live_window(last_at):
                        continue

                    customer_info = conv_data.get("customer_info") or {}
                    user_name = _live_chat_display_name(
                        customer_info.get("name"),
                        config.user_names.get(str(user_id or "")),
                    )
                    phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=customer_info)
                    language = config.user_data_whatsapp.get(user_id, {}).get("user_preferred_lang", "ar")
                    sentiment = conv_data.get("sentiment", "neutral")

                    if state == self.STATE_ASSIGNED:
                        status = "human"
                    elif state == self.STATE_WAITING_OPERATOR:
                        status = "waiting"
                    else:
                        status = "bot"

                    conversations.append(
                        {
                            "conversation_id": conv_doc.id,
                            "user_id": user_id,
                            "user_name": user_name,
                            "user_phone": phone_full,
                            "phone_clean": phone_clean,
                            "last_message": last_msg.get("text", "") if last_msg else "",
                            "last_activity": last_at.isoformat(),
                            "status": status,
                            "conversation_state": state,
                            "language": language,
                            "operator_id": conv_data.get("operator_id"),
                            "sentiment": sentiment,
                            "message_count": len(messages),
                        }
                    )

            conversations.sort(key=lambda x: x["last_activity"], reverse=True)
            if search:
                conversations = self._filter_conversations(conversations, search)
            return conversations
        except Exception as e:
            print(f"⚠️ Legacy active scan failed: {e}")
            return []

    async def _fallback_unified_chats(
        self,
        search: str,
        page: int,
        page_size: int,
        filter_state: str,
    ) -> dict:
        """Removed from request paths. Use scripts/backfill_live_chat_index.py."""
        raise RuntimeError(
            "Legacy Live Chat full-scan is disabled; run scripts/backfill_live_chat_index.py "
            "or POST /api/live-chat/rebuild-index"
        )

    async def _fallback_unified_chats_with_timeout(
        self,
        search: str,
        page: int,
        page_size: int,
        filter_state: str,
    ) -> dict:
        raise RuntimeError(
            "Legacy Live Chat full-scan is disabled; run scripts/backfill_live_chat_index.py "
            "or POST /api/live-chat/rebuild-index"
        )

    async def get_unified_chats(
        self,
        search: str = "",
        page: int = 1,
        page_size: int = 30,
        filter_state: str = "all",
        cursor: str | None = None,
        channel: str = "",
    ) -> Any:
        """
        WhatsApp-style inbox driven ONLY by live_chat_index.
        - Single master list ordered by last_message_at desc
        -  filter by conversation_state badge
        - Optional channel filter (whatsapp|instagram|facebook|tiktok); default all
        - Cursor-based pagination (last_message_at + conversation_id)
        - Search by name / phone against index documents
        """
        search_val = (search or "").strip().lower()
        safe_size = max(1, min(int(page_size), 100))
        state_values = self._state_filter_values(filter_state)
        wanted_channel = normalize_live_chat_channel(channel)
        page_num = max(1, int(page))
        can_use_stale_cache = (
            page_num == 1
            and not search_val
            and not cursor
            and not state_values
            and not wanted_channel
            and bool(self._unified_chats_cache)
        )
        use_cache_fallback = (
            page_num == 1
            and not search_val
            and not cursor
            and not state_values
            and not wanted_channel
            and bool(self._unified_chats_cache)
            and (self._unified_chats_cache_page_size is None or self._unified_chats_cache_page_size == safe_size)
        )
        if use_cache_fallback and self._is_cache_fresh(
            self._unified_chats_cache_time,
            ttl_seconds=self.UNIFIED_CACHE_TTL,
        ):
            print(f"[live_chat:unified] source=memory_cache page={page_num} size={safe_size} search={bool(search_val)}")
            return self._cached_unified_response(page_num, safe_size, filter_state, search)

        try:
            request_started = utc_now()
            db = get_firestore_db()
            if not db:
                stale = self._stale_unified_fallback(page_num, safe_size, filter_state, search)
                if stale:
                    return stale
                return self._empty_unified_response(
                    page_num,
                    safe_size,
                    filter_state,
                    search,
                    source="firestore_missing",
                )

            index_coll = self._index_collection(db)

            # Build base query (ordered for pagination)
            query = index_coll.order_by("last_message_at", direction=firestore.Query.DESCENDING).order_by(
                "conversation_id"
            )

            if state_values:
                if len(state_values) == 1:
                    query = query.where("conversation_state", "==", state_values[0])
                else:
                    query = query.where("conversation_state", "in", state_values)

            start_after_doc = None
            if cursor:
                try:
                    _ts_part, conv_part = cursor.split("|", 1)
                    # Firestore start_after requires DocumentSnapshot; conv_id is the doc ID
                    doc_ref = index_coll.document(conv_part)
                    start_after_doc = await self._run_blocking_with_timeout(
                        lambda: doc_ref.get(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS),
                        self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                    )
                    if not start_after_doc or not start_after_doc.exists:
                        start_after_doc = None
                except Exception:
                    start_after_doc = None

            # Stale index rows can still match Firestore equality on conversation_state; we post-filter
            # by normalized state, so over-fetch when a state filter is active (not "all").
            fetch_limit = safe_size + 1  # fetch one extra to know if there's more
            if (state_values or wanted_channel) and not search_val:
                fetch_limit = min(max((safe_size + 1) * 15, 150), 500)

            def _stream_page(q: Any, after_doc: Any | None = None) -> Any:
                use_q = q
                if after_doc:
                    use_q = use_q.start_after(after_doc)
                return list(
                    use_q.limit(fetch_limit).stream(
                        timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                        retry=None,
                    )
                )

            docs = await self._run_blocking_with_timeout(
                lambda: _stream_page(query, start_after_doc),
                self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
            )
            print(
                f"[live_chat:unified] source=index_page docs={len(docs)} page={page_num} size={safe_size} search={bool(search_val)} filter={filter_state}"
            )

            # If search provided, widen fetch so we find users by phone/name even if inactive for years
            if search_val:
                widen_limit = self.SEARCH_WIDEN_MAX_DOCS

                def _stream_search(q: Any) -> Any:
                    use_q = q
                    if state_values:
                        use_q = use_q
                    return list(
                        use_q.limit(widen_limit).stream(
                            timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                            retry=None,
                        )
                    )

                docs = await self._run_blocking_with_timeout(
                    lambda: _stream_search(query),
                    self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                )
                print(
                    f"[live_chat:unified] source=index_search docs={len(docs)} widen_limit={widen_limit} search={search_val}"
                )

            if not docs:
                stale = self._stale_unified_fallback(page_num, safe_size, filter_state, search)
                if stale:
                    return stale
                # Never N+1 full-scan conversations on the list path.
                # Operators must run scripts/backfill_live_chat_index.py (or rebuild-index API).
                print(
                    "[live_chat:unified] index empty — refusing legacy full scan; run live chat index backfill/rebuild"
                )
                return {
                    "success": True,
                    "chats": [],
                    "total": 0,
                    "page": page_num,
                    "page_size": safe_size,
                    "has_more": False,
                    "next_cursor": None,
                    "index_empty": True,
                    "requires_index_rebuild": True,
                }

            chats: list[dict[str, Any]] = []
            allowed_states = set(state_values) if state_values else None
            for doc in docs:
                data = doc.to_dict() or {}
                state = self._normalize_conversation_state(data)
                # Firestore matched raw conversation_state; stale index rows must not appear under wrong tab
                if allowed_states is not None and state not in allowed_states:
                    continue
                # Extra tab hygiene: index can briefly disagree with human_takeover_active / operator_id
                if allowed_states == {self.STATE_WAITING_OPERATOR}:
                    if data.get("human_takeover_active") is not True:
                        continue
                elif allowed_states == {self.STATE_BOT_ACTIVE}:
                    if data.get("human_takeover_active") is True:
                        continue
                elif allowed_states == {self.STATE_ASSIGNED}:
                    if not data.get("operator_id"):
                        continue
                customer_info = data.get("customer_info") or {}
                user_id = coerce_live_chat_user_id(data, conversation_id=doc.id)
                row_channel = resolve_live_chat_channel(user_id, data)
                if wanted_channel and row_channel != wanted_channel:
                    continue
                user_name = _live_chat_display_name(
                    data.get("user_name"),
                    customer_info.get("name"),
                    config.user_names.get(str(user_id or "")),
                )
                phone_full = data.get("user_phone") or customer_info.get("phone_full") or ""
                phone_clean = data.get("phone_clean") or customer_info.get("phone_clean") or ""
                last_at = data.get("last_message_at") or data.get("last_updated")
                if isinstance(last_at, str):
                    try:
                        last_at = self._parse_timestamp(last_at)
                    except Exception:
                        last_at = utc_now()

                chat_entry = {
                    "conversation_id": doc.id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "phone_number": phone_full,
                    "phone_clean": phone_clean,
                    "last_message_text": data.get("last_message_text", ""),
                    "last_message_at": (
                        last_at.isoformat()
                        if last_at is not None and hasattr(last_at, "isoformat")
                        else str(last_at or "")
                    ),
                    "conversation_state": state,
                    "operator_id": data.get("operator_id"),
                    "operator_name": data.get("operator_name"),
                    # Exposed for dashboard: after release, last_message may still be waiting-queue text — UI must not re-classify as waiting.
                    "human_takeover_active": data.get("human_takeover_active"),
                    "post_release_escalation_suppressed_until": data.get("post_release_escalation_suppressed_until"),
                    "unread_count": data.get("unread_count", 0),
                    "language": data.get("language")
                    or customer_info.get("language")
                    or config.user_data_whatsapp.get(str(user_id or ""), {}).get("user_preferred_lang", "ar"),
                    "sentiment": data.get("sentiment", "neutral"),
                    "message_count": data.get("message_count", 0),
                    "is_new_customer": data.get("is_new_customer", False),
                    "channel": row_channel,
                }
                chats.append(chat_entry)

            if search_val:
                chats = [
                    c
                    for c in chats
                    if search_val in str(c.get("user_name", "")).lower()
                    or search_val in str(c.get("phone_number", "")).lower()
                    or search_val in str(c.get("phone_clean", "")).lower()
                ]
            if wanted_channel:
                chats = [c for c in chats if live_chat_channel_matches(c, wanted_channel)]

            # Always order by last_message_at desc (already sorted by query)
            chats.sort(key=lambda c: (c.get("last_message_at", ""), c.get("conversation_id", "")), reverse=True)

            # Cursor-based pagination: when cursor provided, find start position for Load More
            start_idx = 0
            if cursor:
                try:
                    ts_part, conv_part = cursor.split("|", 1)
                    ts_str = ts_part.strip()
                    for i, c in enumerate(chats):
                        c_ts = str(c.get("last_message_at", ""))
                        c_conv = str(c.get("conversation_id", ""))
                        if (c_ts, c_conv) < (ts_str, conv_part):
                            start_idx = i
                            break
                    else:
                        start_idx = len(chats)
                except Exception:
                    start_idx = 0

            has_more = len(chats) > start_idx + safe_size
            paged = chats[start_idx : start_idx + safe_size]
            paged = [self._to_frontend_chat_format(c) for c in paged]
            next_cursor = None
            if has_more and paged:
                last = paged[-1]
                next_cursor = f"{last.get('last_message_at', '')}|{last.get('conversation_id', '')}"

            total_returned = len(paged)
            if not search_val and not cursor and not state_values and not wanted_channel:
                self._unified_chats_cache = paged
                self._unified_chats_cache_time = utc_now()
                self._unified_chats_cache_has_more = has_more
                self._unified_chats_cache_total = total_returned
                self._unified_chats_cache_next_cursor = next_cursor
                self._unified_chats_cache_page_size = safe_size
                self._persist_unified_cache_to_disk()

            if page_num == 1 and not cursor:
                counters = await self._compute_index_counters()
            else:
                counters = dict(self._index_counters_cache or self._empty_counters())

            elapsed_ms = int((utc_now() - request_started).total_seconds() * 1000)
            print(f"[live_chat:unified] return chats={len(paged)} has_more={has_more} elapsed_ms={elapsed_ms}")

            return {
                "success": True,
                "chats": paged,
                "total": total_returned,
                "page": page,
                "page_size": safe_size,
                "has_more": has_more,
                "next_cursor": next_cursor,
                "filter": filter_state,
                "counters": counters,
                "search": search,
            }
        except Exception as e:
            print(f"❌ Error in get_unified_chats: {e}")
            import traceback

            traceback.print_exc()
            # Never fall back to legacy full-scan on errors — use cache or empty + rebuild signal.
            stale = self._stale_unified_fallback(page_num, safe_size, filter_state, search)
            if stale:
                return stale
            empty = self._empty_unified_response(
                page_num,
                safe_size,
                filter_state,
                search,
                source="index_error",
            )
            if isinstance(empty, dict):
                empty["requires_index_rebuild"] = True
            return empty
