from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore

import config
from services.live_chat_contracts import (
    utc_now,
)
from services.live_chat_service_common import (
    _env_int,
    _live_chat_display_name,
)
from utils.utils import (
    get_firestore_db,
)


class LiveChatTemplatesMixin:
    """Template-send-log chat lookup and index counters."""

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
    INDEX_COUNTERS_CACHE_TTL: Any
    INDEX_COUNTER_SCAN_LIMIT: Any
    STATE_ARCHIVED: Any
    STATE_ASSIGNED: Any
    STATE_BOT_ACTIVE: Any
    STATE_RESOLVED: Any
    STATE_WAITING_OPERATOR: Any
    _empty_counters: Any
    _identity_keys_for_index_chat: Any
    _index_collection: Any
    _is_cache_fresh: Any
    _normalize_conversation_state: Any
    _parse_timestamp: Any
    _run_blocking_with_timeout: Any
    _to_frontend_chat_format: Any

    async def get_chats_by_template_send_log(
        self,
        template_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        scan_limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Match live_chat_index rows to Smart Messaging message_logs (successful template sends).
        Scans up to scan_limit index docs (newest first). Date filter applies to log sent_at (UTC day).
        """
        from services.message_logs_service import message_logs_service
        from services.smart_messaging_catalog import normalize_template_id

        tid = normalize_template_id((template_id or "").strip())
        if not tid:
            return {
                "success": False,
                "error": "template_id is required",
                "chats": [],
                "log_entries_matched": 0,
                "distinct_recipients": 0,
                "matched_chats": 0,
                "index_scanned": 0,
            }

        max_scan = scan_limit
        if max_scan is None or int(max_scan) <= 0:
            max_scan = _env_int("LIVE_CHAT_TEMPLATE_FILTER_SCAN_LIMIT", 4000)
        max_scan = max(100, min(int(max_scan), 20000))

        df = (date_from or "").strip() or None
        dt = (date_to or "").strip() or None

        recipient_keys, latest_sent, log_rows = message_logs_service.recipient_phone_keys_for_template(
            tid, date_from=df, date_to=dt
        )

        if not recipient_keys:
            return {
                "success": True,
                "chats": [],
                "template_id": tid,
                "log_entries_matched": log_rows,
                "distinct_recipients": 0,
                "matched_chats": 0,
                "index_scanned": 0,
                "date_from": df or "",
                "date_to": dt or "",
                "message": "No send log entries for this template in the selected date range.",
            }

        db = get_firestore_db()
        if not db:
            return {
                "success": False,
                "error": "firestore_unavailable",
                "chats": [],
                "template_id": tid,
                "log_entries_matched": log_rows,
                "distinct_recipients": len(recipient_keys),
                "matched_chats": 0,
                "index_scanned": 0,
            }

        index_coll = self._index_collection(db)

        def _stream() -> Any:
            return list(
                index_coll.order_by("last_message_at", direction=firestore.Query.DESCENDING)
                .order_by("conversation_id")
                .limit(max_scan)
                .stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS, retry=None)
            )

        try:
            docs = await self._run_blocking_with_timeout(
                _stream,
                self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
            )
        except Exception as e:
            print(f"❌ get_chats_by_template_send_log stream error: {e}")
            return {
                "success": False,
                "error": str(e),
                "chats": [],
                "template_id": tid,
                "log_entries_matched": log_rows,
                "distinct_recipients": len(recipient_keys),
                "matched_chats": 0,
                "index_scanned": 0,
            }

        matched: list[dict[str, Any]] = []
        for doc in docs or []:
            data = doc.to_dict() or {}
            state = self._normalize_conversation_state(data)
            customer_info = data.get("customer_info") or {}
            user_id = data.get("user_id")
            user_name = _live_chat_display_name(
                data.get("user_name"),
                customer_info.get("name"),
                config.user_names.get(str(user_id or "")),
            )
            phone_full = data.get("user_phone") or customer_info.get("phone_full") or ""
            phone_clean = data.get("phone_clean") or customer_info.get("phone_clean") or ""

            id_keys = self._identity_keys_for_index_chat(user_id, phone_full, phone_clean)
            overlap = id_keys & recipient_keys
            if not overlap:
                continue

            matched_key = sorted(overlap)[0]
            sent_hint = latest_sent.get(matched_key) or ""

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
                    last_at.isoformat() if last_at is not None and hasattr(last_at, "isoformat") else str(last_at or "")
                ),
                "conversation_state": state,
                "operator_id": data.get("operator_id"),
                "human_takeover_active": data.get("human_takeover_active"),
                "post_release_escalation_suppressed_until": data.get("post_release_escalation_suppressed_until"),
                "unread_count": data.get("unread_count", 0),
                "language": data.get("language")
                or customer_info.get("language")
                or config.user_data_whatsapp.get(str(user_id or ""), {}).get("user_preferred_lang", "ar"),
                "sentiment": data.get("sentiment", "neutral"),
                "message_count": data.get("message_count", 0),
                "is_new_customer": data.get("is_new_customer", False),
                "template_send_logged_at": sent_hint,
            }
            matched.append(self._to_frontend_chat_format(chat_entry))

        matched.sort(
            key=lambda c: (c.get("last_message_at", ""), c.get("conversation_id", "")),
            reverse=True,
        )

        return {
            "success": True,
            "chats": matched,
            "template_id": tid,
            "log_entries_matched": log_rows,
            "distinct_recipients": len(recipient_keys),
            "matched_chats": len(matched),
            "index_scanned": len(docs or []),
            "date_from": df or "",
            "date_to": dt or "",
        }

    async def _compute_index_counters(self) -> Any:
        """Compute dashboard counters directly from live_chat_index (best-effort, capped for performance)."""
        if self._is_cache_fresh(
            self._index_counters_cache_time,
            ttl_seconds=self.INDEX_COUNTERS_CACHE_TTL,
        ):
            print("[live_chat:counters] source=cache")
            return dict(self._index_counters_cache)

        counters = self._empty_counters()
        try:
            db = get_firestore_db()
            if not db:
                return counters
            index_coll = self._index_collection(db)
            # Cap to avoid massive scans on every dashboard refresh.
            docs = await asyncio.to_thread(
                lambda: list(
                    index_coll.order_by("last_message_at", direction=firestore.Query.DESCENDING)
                    .limit(self.INDEX_COUNTER_SCAN_LIMIT)
                    .stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS)
                ),
            )
            print(f"[live_chat:counters] source=index docs_scanned={len(docs)} limit={self.INDEX_COUNTER_SCAN_LIMIT}")
            for doc in docs:
                data = doc.to_dict() or {}
                state = self._normalize_conversation_state(data)
                counters["all"] += 1
                if state == self.STATE_WAITING_OPERATOR:
                    counters["waiting"] += 1
                if state == self.STATE_ASSIGNED:
                    counters["with_operator"] += 1
                if state == self.STATE_BOT_ACTIVE:
                    counters["bot_active"] += 1
                if state in {self.STATE_RESOLVED, self.STATE_ARCHIVED}:
                    counters["closed"] += 1
            self._index_counters_cache = dict(counters)
            self._index_counters_cache_time = utc_now()
            return counters
        except Exception as e:
            print(f"⚠️ counter computation failed: {e}")
            if self._index_counters_cache:
                return dict(self._index_counters_cache)
            return counters
