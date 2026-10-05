from __future__ import annotations

from typing import Any

from services.live_chat.channel import (
    normalize_live_chat_channel,
)
from services.live_chat.tenant import (
    normalize_live_chat_tenant_id,
)
from services.persistence.chat_store import ChatTenantRequired, counters_for_tenant, list_inbox


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
    _counters_for_tenant: Any
    _empty_unified_response: Any
    _filter_conversations: Any
    _get_users_collection: Any
    _index_collection: Any
    _index_recency_query: Any
    _index_counters_cache: Any
    _is_cache_fresh: Any
    _is_live_window: Any
    _normalize_conversation_state: Any
    _parse_timestamp: Any
    _persist_unified_cache_to_disk: Any
    _resolve_user_phone: Any
    _run_blocking_with_timeout: Any
    _state_filter_values: Any
    _store_unified_inbox: Any
    _stream_tenant_index_docs: Any
    _stale_unified_fallback: Any
    _stream_conversations_for_users: Any
    _stream_user_docs: Any
    _tenant_inbox_slot: Any
    _to_frontend_chat_format: Any
    _visible_chat_messages: Any

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
        tenant_id: str = "",
    ) -> Any:
        """WhatsApp-style inbox from Postgres, scoped to session tenant_id."""
        safe_size = max(1, min(int(page_size), 100))
        page_num = max(1, int(page))
        tid = normalize_live_chat_tenant_id(tenant_id)
        if not tid:
            return self._empty_unified_response(
                page_num, safe_size, filter_state, search, source="missing_tenant", tenant_id=""
            )
        try:
            page_rows = list_inbox(
                tid,
                limit=safe_size,
                cursor=cursor,
                search=search,
                states=list(self._state_filter_values(filter_state) or []),
                channel=normalize_live_chat_channel(channel) or "",
            )
            counters = counters_for_tenant(tid)
        except ChatTenantRequired:
            return self._empty_unified_response(
                page_num, safe_size, filter_state, search, source="missing_tenant", tenant_id=""
            )
        except Exception as exc:
            print(f"[live_chat:unified] postgres inbox failed: {type(exc).__name__}")
            empty = self._empty_unified_response(
                page_num, safe_size, filter_state, search, source="index_error", tenant_id=tid
            )
            if isinstance(empty, dict):
                empty["requires_index_rebuild"] = True
            return empty
        chats = []
        for row in page_rows["threads"]:
            chats.append(
                self._to_frontend_chat_format(
                    {
                        "conversation_id": row["conversation_id"],
                        "user_id": row["user_id"],
                        "user_name": row["user_name"],
                        "phone_number": row["user_phone"],
                        "phone_clean": row["user_phone"],
                        "last_message_text": row["last_message_text"],
                        "last_message_at": row["last_message_at"],
                        "conversation_state": row["conversation_state"],
                        "operator_id": row["operator_id"],
                        "unread_count": row["unread_count"],
                        "message_count": row["message_count"],
                        "channel": row["channel"],
                        "tenant_id": row["tenant_id"],
                        "human_takeover_active": bool(row["human_takeover_active"]),
                    }
                )
            )
        return {
            "success": True,
            "chats": chats,
            "total": len(chats),
            "page": page,
            "page_size": safe_size,
            "has_more": page_rows["has_more"],
            "next_cursor": page_rows["next_cursor"],
            "filter": filter_state,
            "counters": counters,
            "search": search,
        }
