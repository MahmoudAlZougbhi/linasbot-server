# -*- coding: utf-8 -*-
"""
Live Chat Service - Canonical conversation_state
- 6-hour time filter for active conversations
- Canonical conversation_state drives UI and persistence
- Firestore is source of truth; caches only accelerate reads
- Auto-reopen on new message
"""

import datetime
import asyncio
import json
import os
import re
from typing import List, Dict, Optional, Any, Tuple, Union
from collections import defaultdict
from google.cloud import firestore
import config
from services.live_chat_contracts import (
    dedupe_messages as contract_dedupe_messages,
    normalize_conversation_document,
    parse_timestamp_utc,
    utc_now,
)
from utils.utils import get_firestore_db, set_human_takeover_status, get_canonical_user_id_and_phone
from utils.phone_utils import normalize_phone
from services.media_service import build_whatsapp_audio_delivery_url


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class LiveChatService:
    """Service for managing live chat operations with canonical state"""

    APP_ID = "linas-ai-bot-backend"

    # Time window for active conversations (6 hours - "live" = currently with AI)
    ACTIVE_TIME_WINDOW = 6 * 60 * 60  # 6 hours

    # Cache configuration (tuned for quota safety)
    CACHE_TTL = _env_int("LIVECHAT_CACHE_TTL_SECONDS", 45)
    PHONE_MAPPING_CACHE_TTL = _env_int("LIVECHAT_PHONE_MAPPING_CACHE_TTL_SECONDS", 120)
    UNIFIED_CACHE_TTL = _env_int("LIVECHAT_UNIFIED_CACHE_TTL_SECONDS", 12)
    FIRESTORE_FETCH_PARALLELISM = 24
    FIRESTORE_DOC_TIMEOUT_SECONDS = _env_float("LIVECHAT_DOC_TIMEOUT_SECONDS", 4)
    FIRESTORE_QUERY_TIMEOUT_SECONDS = _env_float("LIVECHAT_QUERY_TIMEOUT_SECONDS", 4)
    RECENT_MESSAGES_IN_INDEX = 50
    INDEX_READ_TIMEOUT_SECONDS = _env_float("LIVECHAT_INDEX_READ_TIMEOUT_SECONDS", 3)
    INDEX_WRITE_TIMEOUT_SECONDS = _env_float("LIVECHAT_INDEX_WRITE_TIMEOUT_SECONDS", 4)
    INDEX_REFRESH_TIMEOUT_SECONDS = _env_float("LIVECHAT_INDEX_REFRESH_TIMEOUT_SECONDS", 4)
    INDEX_WRITE_COOLDOWN_SECONDS = _env_int("LIVECHAT_INDEX_WRITE_COOLDOWN_SECONDS", 180)
    INDEX_COUNTERS_CACHE_TTL = _env_int("LIVECHAT_INDEX_COUNTERS_CACHE_TTL_SECONDS", 180)
    INDEX_COUNTER_SCAN_LIMIT = _env_int("LIVECHAT_INDEX_COUNTER_SCAN_LIMIT", 250)
    INDEX_REFRESH_MIN_INTERVAL_SECONDS = _env_int("LIVECHAT_INDEX_REFRESH_MIN_INTERVAL_SECONDS", 120)
    SEARCH_WIDEN_MAX_DOCS = _env_int("LIVECHAT_SEARCH_WIDEN_MAX_DOCS", 300)
    ENABLE_INDEX_BACKFILL_ON_READ = _env_bool("LIVECHAT_ENABLE_INDEX_BACKFILL_ON_READ", False)
    ENABLE_WAITING_QUEUE_FALLBACK_SCAN = _env_bool("LIVECHAT_ENABLE_WAITING_QUEUE_FALLBACK_SCAN", False)
    FALLBACK_USERS_STREAM_LIMIT = 80
    FALLBACK_UNIFIED_TIMEOUT_SECONDS = _env_int("LIVECHAT_FALLBACK_UNIFIED_TIMEOUT_SECONDS", 8)

    # Canonical conversation states
    STATE_BOT_ACTIVE = "bot_active"
    STATE_WAITING_OPERATOR = "waiting_for_operator"
    STATE_ASSIGNED = "assigned_to_operator"
    STATE_RESOLVED = "resolved"
    STATE_ARCHIVED = "archived"

    INDEX_COLLECTION = "live_chat_index"

    def __init__(self):
        self.operator_status = defaultdict(lambda: "available")
        self.operator_sessions = {}
        # Cache for active conversations
        self._conversations_cache = None
        self._conversations_cache_time = None
        # Cache for waiting queue
        self._queue_cache = None
        self._queue_cache_time = None
        # Cache for static phone<->room mapping file
        self._phone_to_room_cache = {}
        self._room_to_phone_cache = {}
        self._phone_mapping_cache_time = None
        # Cache for unified chats (WhatsApp-style list)
        self._unified_chats_cache = []
        self._unified_chats_cache_time = None
        self._unified_chats_cache_has_more = False
        self._unified_chats_cache_total = 0
        self._unified_chats_cache_next_cursor = None
        self._unified_chats_cache_page_size = None
        self._index_counters_cache = self._empty_counters()
        self._index_counters_cache_time = None
        self._index_write_paused_until = None
        # Prevent duplicate index writes for identical payloads.
        self._index_signature_cache = {}
        # Throttle read-path index refreshes for the same conversation.
        self._read_path_refresh_tracker = {}

    # ---------- State + index helpers ----------
    def _normalize_conversation_state(self, conv_data: dict) -> str:
        """
        Resolve a safe canonical conversation_state without downgrading valid states.
        Priority:
        1) Preserve existing valid conversation_state
        2) Derive from lifecycle markers (archived/resolved/operator takeover)
        3) Fallback to waiting/bot
        """

        data = conv_data or {}
        state = data.get("conversation_state")
        valid_states = {
            self.STATE_BOT_ACTIVE,
            self.STATE_WAITING_OPERATOR,
            self.STATE_ASSIGNED,
            self.STATE_RESOLVED,
            self.STATE_ARCHIVED,
        }

        if state in valid_states:
            return state

        status = str(data.get("status", "")).lower()
        resolved_at = data.get("resolved_at")
        archived_at = data.get("archived_at")
        human_takeover = bool(data.get("human_takeover_active"))
        operator_id = data.get("operator_id")

        if archived_at or status == "archived":
            return self.STATE_ARCHIVED
        if resolved_at or status in {"resolved", "closed"}:
            return self.STATE_RESOLVED
        if human_takeover:
            return self.STATE_ASSIGNED if operator_id else self.STATE_WAITING_OPERATOR
        if status in {"waiting", "waiting_for_operator", "pending", "waiting_human"}:
            return self.STATE_WAITING_OPERATOR

        return self.STATE_BOT_ACTIVE

    def _is_live_window(self, ts: datetime.datetime) -> bool:
        return bool(ts) and (utc_now() - ts).total_seconds() <= self.ACTIVE_TIME_WINDOW

    def _state_filter_values(self, filter_key: str):
        key = (filter_key or "").lower()
        if key in {"waiting", "waiting_for_operator"}:
            return [self.STATE_WAITING_OPERATOR]
        if key in {"with_operator", "assigned"}:
            return [self.STATE_ASSIGNED]
        if key in {"bot", "bot_active"}:
            return [self.STATE_BOT_ACTIVE]
        if key in {"closed", "resolved_or_archived"}:
            return [self.STATE_RESOLVED, self.STATE_ARCHIVED]
        return []

    def _conversation_state_to_status(self, state: str) -> str:
        """Map canonical conversation_state to frontend status (bot, waiting_human, human)."""
        if state == self.STATE_ASSIGNED:
            return "human"
        if state == self.STATE_WAITING_OPERATOR:
            return "waiting_human"
        if state in {self.STATE_RESOLVED, self.STATE_ARCHIVED}:
            return "closed"
        return "bot"

    def _to_frontend_chat_format(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich chat entry with frontend-expected fields (status, last_message, user_phone, last_activity)."""
        state = chat.get("conversation_state", self.STATE_BOT_ACTIVE)
        last_text = chat.get("last_message_text", "")
        last_at = chat.get("last_message_at", "")
        out = dict(chat)
        out["status"] = self._conversation_state_to_status(state)
        out["user_phone"] = chat.get("user_phone") or chat.get("phone_number", "")
        out["last_activity"] = last_at
        out["last_message"] = (
            {"content": last_text, "timestamp": last_at, "is_user": False}
            if last_text or last_at
            else None
        )
        return out

    def _index_collection(self, db):
        return db.collection("artifacts").document(self.APP_ID).collection(self.INDEX_COLLECTION)

    def _empty_counters(self) -> Dict[str, int]:
        return {
            "all": 0,
            "waiting": 0,
            "with_operator": 0,
            "bot_active": 0,
            "closed": 0,
        }

    def _is_index_write_paused(self) -> bool:
        if self._index_write_paused_until is None:
            return False
        return utc_now() < self._index_write_paused_until

    def _pause_index_writes(self, reason: str):
        self._index_write_paused_until = utc_now() + datetime.timedelta(
            seconds=self.INDEX_WRITE_COOLDOWN_SECONDS
        )
        print(
            f"⚠️ Pausing live_chat_index writes for {self.INDEX_WRITE_COOLDOWN_SECONDS}s: {reason}"
        )

    def _should_schedule_read_path_refresh(self, conversation_id: str) -> bool:
        now = utc_now()
        last = self._read_path_refresh_tracker.get(conversation_id)
        if last:
            elapsed = (now - last).total_seconds()
            if elapsed < self.INDEX_REFRESH_MIN_INTERVAL_SECONDS:
                return False
        self._read_path_refresh_tracker[conversation_id] = now
        return True

    def _cached_unified_response(
        self, page: int, page_size: int, filter_state: str, search: str
    ) -> Dict[str, Any]:
        chats = list(self._unified_chats_cache or [])
        counters = dict(self._index_counters_cache or self._empty_counters())
        total = int(self._unified_chats_cache_total or len(chats))
        return {
            "success": True,
            "chats": chats,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": bool(self._unified_chats_cache_has_more),
            "next_cursor": self._unified_chats_cache_next_cursor,
            "filter": filter_state,
            "counters": counters,
            "search": search,
            "source": "cache",
        }

    def _empty_unified_response(
        self, page: int, page_size: int, filter_state: str, search: str, source: str
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "chats": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "next_cursor": None,
            "filter": filter_state,
            "counters": dict(self._index_counters_cache or self._empty_counters()),
            "search": search,
            "source": source,
        }

    async def _run_blocking_with_timeout(self, fn, timeout_seconds: float):
        timeout = max(0.1, float(timeout_seconds or 0))
        task = asyncio.create_task(asyncio.to_thread(fn))
        done, pending = await asyncio.wait({task}, timeout=timeout)
        if not done:
            for p in pending:
                p.cancel()
            raise asyncio.TimeoutError()
        return task.result()

    async def _get_doc_with_timeout(self, doc_ref, timeout_seconds: Optional[float] = None):
        """Guard Firestore doc reads so UI requests don't hang indefinitely."""
        timeout = timeout_seconds or self.FIRESTORE_DOC_TIMEOUT_SECONDS
        try:
            return await self._run_blocking_with_timeout(
                lambda: doc_ref.get(timeout=timeout),
                timeout,
            )
        except Exception as e:
            lowered = str(e).lower()
            if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
                raise asyncio.TimeoutError() from e
            raise

    def _format_single_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Format one raw message to API response shape (for index cache and full doc path)."""
        meta = msg.get("metadata") or {}
        text_value = msg.get("text")
        if text_value is None or text_value == "":
            text_value = msg.get("content", "")
        handled = meta.get("handled_by")
        if not handled:
            if meta.get("source") == "qa_database":
                handled = "bot"
            elif msg.get("role") == "operator":
                handled = "human"
            else:
                handled = "ai"
        ts_str = self._parse_timestamp(msg.get("timestamp")).isoformat()
        message_id = msg.get("message_id") or meta.get("message_id") or meta.get("source_message_id") or f"ts_{ts_str}"
        msg_data = {
            "message_id": str(message_id),
            "timestamp": ts_str,
            "is_user": msg.get("role") == "user",
            "content": text_value,
            "text": text_value,
            "type": msg.get("type", "text"),
            "handled_by": handled,
            "role": msg.get("role"),
        }
        audio_url = msg.get("audio_url") or meta.get("audio_url")
        if audio_url:
            msg_data["audio_url"] = audio_url
        image_url = msg.get("image_url") or meta.get("image_url")
        if image_url:
            msg_data["image_url"] = image_url
        if meta.get("reply_source"):
            msg_data["reply_source"] = meta["reply_source"]
        if meta.get("faq_match"):
            msg_data["metadata"] = msg_data.get("metadata") or {}
            msg_data["metadata"]["faq_match"] = meta["faq_match"]
        return msg_data

    async def _sync_index_from_source(self, user_id: str, conversation_id: str, *, allow_state_backfill: bool = False) -> Dict[str, Any]:
        """Read canonical conversation from Firestore, normalize, and upsert index entry."""
        db = get_firestore_db()
        if not db:
            return {"written": False, "reason": "firestore_missing"}

        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
        conv_ref = (
            db.collection("artifacts")
            .document(self.APP_ID)
            .collection("users")
            .document(canonical_user_id)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            .document(conversation_id)
        )

        conv_snap = await self._get_doc_with_timeout(
            conv_ref, timeout_seconds=self.FIRESTORE_QUERY_TIMEOUT_SECONDS
        )
        if not conv_snap.exists:
            return {"written": False, "reason": "missing"}

        raw_payload = conv_snap.to_dict() or {}
        conv_data = self._canonical_conversation(conversation_id, canonical_user_id, raw_payload)
        entry = self._build_index_entry(canonical_user_id, conv_data, conv_data.get("visible_messages", []))

        state_backfill = False
        if allow_state_backfill and not raw_payload.get("conversation_state") and conv_data.get("conversation_state"):
            try:
                await asyncio.to_thread(conv_ref.update, {"conversation_state": conv_data["conversation_state"]})
                state_backfill = True
            except Exception as e:
                print(f"⚠️ Failed to backfill conversation_state for {conversation_id}: {e}")

        await self._upsert_index_entry(entry)

        return {
            "written": True,
            "state_backfill": state_backfill,
            "conversation_state": conv_data.get("conversation_state"),
        }

    def _canonical_conversation(self, conversation_id: str, user_id: str, payload: dict) -> dict:
        """Normalize Firestore conversation payload and enrich with derived fields."""
        conv_data = normalize_conversation_document(
            conversation_id=conversation_id,
            user_id=user_id,
            payload=payload or {},
        )

        state = self._normalize_conversation_state(conv_data)
        conv_data["conversation_state"] = state
        conv_data["raw_conversation_state"] = payload.get("conversation_state") if isinstance(payload, dict) else None

        messages = conv_data.get("messages", []) or []
        visible_messages = self._visible_chat_messages(messages)
        last_message = visible_messages[-1] if visible_messages else (messages[-1] if messages else {})
        last_ts = conv_data.get("last_message_at") or conv_data.get("last_updated") or conv_data.get("timestamp")
        if not last_ts and last_message:
            last_ts = self._parse_timestamp(last_message.get("timestamp"))
        if not last_ts:
            last_ts = utc_now()

        conv_data["visible_messages"] = visible_messages
        conv_data["last_message_at"] = last_ts
        if last_message:
            conv_data["last_message_text"] = last_message.get("text") or last_message.get("content", "")
        else:
            conv_data["last_message_text"] = ""
        conv_data["message_count"] = len(visible_messages)

        return conv_data

    async def rebuild_index_from_firestore(
        self,
        max_users: Optional[int] = None,
        max_conversations_per_user: Optional[int] = None,
        set_conversation_state: bool = True,
        return_details: bool = False,
    ) -> Union[int, Dict[str, int]]:
        """One-time (or manual) rebuild of live_chat_index from Firestore conversations.

        Returns number of index entries written.
        """
        db = get_firestore_db()
        if not db:
            print("⚠️ Firestore not initialized; cannot rebuild index")
            return 0

        users_collection = self._get_users_collection()
        if users_collection is None:
            print("⚠️ Users collection missing; cannot rebuild index")
            return 0

        users_docs = await self._stream_user_docs(users_collection, limit=max_users)
        user_ids = [doc.id for doc in users_docs]

        # Stream conversations per user (optionally limited per user)
        conversation_results = []
        semaphore = asyncio.Semaphore(self.FIRESTORE_FETCH_PARALLELISM)

        async def _bounded(user_id: str):
            async with semaphore:
                try:
                    conversations_collection = users_collection.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                    q = conversations_collection.order_by("last_updated", direction=firestore.Query.DESCENDING)
                    if max_conversations_per_user:
                        q = q.limit(max_conversations_per_user)
                    docs = await asyncio.to_thread(lambda: list(q.stream()))
                    return user_id, docs
                except Exception as e:
                    print(f"⚠️ Error streaming conversations for {user_id}: {e}")
                    return user_id, []

        conversation_results = await asyncio.gather(*[_bounded(uid) for uid in user_ids])

        total_written = 0
        repaired_states = 0
        skipped_missing = 0

        for user_id, conv_docs in conversation_results:
            for conv_doc in conv_docs:
                result = await self._sync_index_from_source(
                    user_id,
                    conv_doc.id,
                    allow_state_backfill=set_conversation_state,
                )
                if result.get("written"):
                    total_written += 1
                    if result.get("state_backfill"):
                        repaired_states += 1
                else:
                    skipped_missing += 1

        print(
            f"📦 Rebuilt live_chat_index entries: written={total_written} repaired_states={repaired_states} missing={skipped_missing}"
        )
        if return_details:
            return {
                "written": total_written,
                "repaired_states": repaired_states,
                "skipped_missing": skipped_missing,
            }
        return total_written

    def _build_index_entry(self, user_id: str, conv_data: dict, messages: list) -> dict:
        state = self._normalize_conversation_state(conv_data)
        customer_info = conv_data.get("customer_info", {}) or {}
        user_name = customer_info.get("name") or config.user_names.get(user_id) or "Unknown Customer"
        phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=customer_info)
        last_ts = conv_data.get("last_message_at") or conv_data.get("last_updated") or utc_now()
        if isinstance(last_ts, str):
            try:
                last_ts = self._parse_timestamp(last_ts)
            except Exception:
                last_ts = utc_now()

        last_message_text = conv_data.get("last_message_text", "")
        sentiment = conv_data.get("sentiment", "neutral")
        unread_count = conv_data.get("unread_count") or 0
        language = config.user_data_whatsapp.get(user_id, {}).get("user_preferred_lang", "ar")
        message_count = conv_data.get("message_count", len(messages))
        is_live = state in {self.STATE_BOT_ACTIVE, self.STATE_WAITING_OPERATOR, self.STATE_ASSIGNED} and self._is_live_window(last_ts)

        recent_messages = []
        if messages:
            tail = messages[-self.RECENT_MESSAGES_IN_INDEX:] if len(messages) > self.RECENT_MESSAGES_IN_INDEX else messages
            for m in tail:
                try:
                    recent_messages.append(self._format_single_message(m))
                except Exception:
                    pass

        out = {
            "conversation_id": conv_data.get("conversation_id"),
            "user_id": user_id,
            "user_name": user_name,
            "user_phone": phone_full,
            "phone_clean": phone_clean,
            "last_message_text": last_message_text,
            "last_message_at": last_ts,
            "message_count": message_count,
            "conversation_state": state,
            "operator_id": conv_data.get("operator_id"),
            "unread_count": unread_count,
            "sentiment": sentiment,
            "is_live": is_live,
            "language": language,
            "customer_info": customer_info,
        }
        if recent_messages:
            out["recent_messages"] = recent_messages
        return out

    async def _upsert_index_entry(self, entry: dict):
        try:
            db = get_firestore_db()
            if not db or not entry:
                return
            if self._is_index_write_paused():
                return
            conv_id = entry.get("conversation_id")
            if not conv_id:
                return

            payload = dict(entry)
            if isinstance(payload.get("last_message_at"), str):
                try:
                    payload["last_message_at"] = self._parse_timestamp(payload["last_message_at"])
                except Exception:
                    payload["last_message_at"] = utc_now()

            signature = (
                str(payload.get("last_message_at")),
                str(payload.get("last_message_text", "")),
                int(payload.get("message_count") or 0),
                str(payload.get("conversation_state") or ""),
                str(payload.get("operator_id") or ""),
                int(payload.get("unread_count") or 0),
            )
            if self._index_signature_cache.get(conv_id) == signature:
                print(f"[live_chat:index] skip unchanged write conv={conv_id}")
                return

            idx = self._index_collection(db).document(conv_id)
            await asyncio.to_thread(
                lambda: idx.set(payload, timeout=self.INDEX_WRITE_TIMEOUT_SECONDS)
            )
            self._index_signature_cache[conv_id] = signature
        except Exception as e:
            print(f"⚠️ Failed upserting index entry for {entry.get('conversation_id')}: {e}")
            lowered = str(e).lower()
            if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
                self._pause_index_writes("index write timeout")
            if "429" in lowered or "quota" in lowered or "resource exhausted" in lowered:
                self._pause_index_writes(str(e))

    async def _refresh_index_for_conversation(self, user_id: str, conv_id: str):
        try:
            if self._is_index_write_paused():
                return
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            result = await asyncio.wait_for(
                self._sync_index_from_source(
                    canonical_user_id, conv_id, allow_state_backfill=False
                ),
                timeout=self.INDEX_REFRESH_TIMEOUT_SECONDS,
            )
            if not result.get("written"):
                print(f"⚠️ [index-refresh] skipped user={canonical_user_id} conv={conv_id} reason={result.get('reason')}")
                return
            print(
                f"🔄 [index-refresh] rebuilt index user={canonical_user_id} conv={conv_id} state={result.get('conversation_state')}"
            )
        except asyncio.TimeoutError:
            print(f"⚠️ [index-refresh] timeout user={user_id} conv={conv_id}")
        except Exception as e:
            print(f"⚠️ Failed to refresh index for {conv_id}: {e}")

    def invalidate_cache(self):
        """Clear service caches so UI reads latest state."""
        self._conversations_cache = None
        self._conversations_cache_time = None
        self._queue_cache = None
        self._queue_cache_time = None
        self._unified_chats_cache = []
        self._unified_chats_cache_time = None
        self._unified_chats_cache_has_more = False
        self._unified_chats_cache_total = 0
        self._unified_chats_cache_next_cursor = None
        self._unified_chats_cache_page_size = None
        self._index_counters_cache = self._empty_counters()
        self._index_counters_cache_time = None

    def _dedupe_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return contract_dedupe_messages(messages)

    def _is_smart_message(self, message: Dict[str, Any]) -> bool:
        metadata = (message or {}).get("metadata", {}) or {}
        return metadata.get("source") == "smart_message"

    def _visible_chat_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Live Chat UI shows all messages including smart messages (scheduled/sent from Smart Messaging).
        Operators need to see the full conversation including automated messages.
        """
        return list(messages or [])

    def _is_cache_fresh(self, cache_time: Optional[datetime.datetime], ttl_seconds: Optional[int] = None) -> bool:
        if cache_time is None:
            return False
        ttl = ttl_seconds or self.CACHE_TTL
        return (utc_now() - cache_time).total_seconds() < ttl

    def _get_users_collection(self):
        db = get_firestore_db()
        if not db:
            return None
        return db.collection("artifacts").document(self.APP_ID).collection("users")

    # Limit users scanned when no search - speeds up first load (150 users ≈ top conversations)
    USERS_STREAM_LIMIT = 150

    async def _stream_user_docs(self, users_collection, limit: Optional[int] = None):
        if users_collection is None:
            return []
        try:
            q = users_collection.order_by("last_activity", direction=firestore.Query.DESCENDING)
            if limit is not None:
                q = q.limit(limit)
            return await asyncio.to_thread(
                lambda: list(q.stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS))
            )
        except Exception:
            try:
                return await asyncio.to_thread(
                    lambda: list(
                        users_collection.stream(
                            timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS
                        )
                    )
                )
            except Exception:
                return []

    async def _stream_user_conversations(self, users_collection, user_id: str):
        try:
            conversations_collection = users_collection.document(user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            )
            conversations_docs = await asyncio.to_thread(
                lambda: list(
                    conversations_collection.stream(
                        timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS
                    )
                )
            )
            return user_id, conversations_docs
        except Exception as e:
            print(f"⚠️ Error fetching conversations for user {user_id}: {e}")
            return user_id, []

    async def _stream_conversations_for_users(self, users_collection, user_ids: List[str]):
        semaphore = asyncio.Semaphore(self.FIRESTORE_FETCH_PARALLELISM)

        async def _bounded_fetch(uid: str):
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

    def _paginate(self, items: List[Dict[str, Any]], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int, int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 1000))
        total_items = len(items)
        total_pages = max(1, (total_items + safe_page_size - 1) // safe_page_size)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return items[start:end], total_items, total_pages

    async def _legacy_active_scan_for_fallback(self, search: Optional[str] = None, user_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lightweight scan of conversations (legacy path) used only as a safety fallback when index is empty."""
        users_collection = self._get_users_collection()
        if users_collection is None:
            return []

        try:
            users_docs = await self._stream_user_docs(users_collection, limit=user_limit)
            user_ids = [doc.id for doc in users_docs]
            conversation_results = await self._stream_conversations_for_users(users_collection, user_ids)

            conversations: List[Dict[str, Any]] = []
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
                    last_at = self._parse_timestamp(last_msg.get("timestamp")) if last_msg else conv_data.get("last_updated") or current_time
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
                    user_name = customer_info.get("name") or config.user_names.get(user_id) or "Unknown Customer"
                    phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=customer_info)
                    language = config.user_data_whatsapp.get(user_id, {}).get("user_preferred_lang", "ar")
                    sentiment = conv_data.get("sentiment", "neutral")

                    if state == self.STATE_ASSIGNED:
                        status = "human"
                    elif state == self.STATE_WAITING_OPERATOR:
                        status = "waiting"
                    else:
                        status = "bot"

                    conversations.append({
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
                    })

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
    ) -> Dict[str, Any]:
        """Resilient inbox loader that reads source conversations directly when index is empty/unavailable."""
        users_collection = self._get_users_collection()
        if users_collection is None:
            return {"success": False, "chats": [], "total": 0, "has_more": False, "error": "firestore_missing"}

        search_val = (search or "").strip().lower()
        state_values = self._state_filter_values(filter_state)
        safe_size = max(1, min(int(page_size), 100))

        try:
            users_docs = await self._stream_user_docs(
                users_collection, limit=self.FALLBACK_USERS_STREAM_LIMIT
            )
            user_ids = [doc.id for doc in users_docs]
            conversation_results = await self._stream_conversations_for_users(users_collection, user_ids)

            chats: List[Dict[str, Any]] = []
            counters = {
                "all": 0,
                "waiting": 0,
                "with_operator": 0,
                "bot_active": 0,
                "closed": 0,
            }

            for result in conversation_results:
                if isinstance(result, Exception):
                    continue
                user_id, conv_docs = result
                for conv_doc in conv_docs:
                    payload = conv_doc.to_dict() or {}
                    conv_data = self._canonical_conversation(conv_doc.id, user_id, payload)
                    state = conv_data.get("conversation_state")
                    if state_values and state not in state_values:
                        continue

                    customer_info = conv_data.get("customer_info") or {}
                    user_name = customer_info.get("name") or config.user_names.get(user_id) or "Unknown Customer"
                    phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=customer_info)
                    last_at = conv_data.get("last_message_at") or utc_now()
                    if isinstance(last_at, str):
                        try:
                            last_at = self._parse_timestamp(last_at)
                        except Exception:
                            last_at = utc_now()

                    chat_entry = {
                        "conversation_id": conv_doc.id,
                        "user_id": user_id,
                        "user_name": user_name,
                        "phone_number": phone_full,
                        "phone_clean": phone_clean,
                        "last_message_text": conv_data.get("last_message_text", ""),
                        "last_message_at": last_at.isoformat(),
                        "conversation_state": state,
                        "operator_id": conv_data.get("operator_id"),
                        "unread_count": conv_data.get("unread_count", 0),
                        "language": config.user_data_whatsapp.get(user_id, {}).get("user_preferred_lang", "ar"),
                        "sentiment": conv_data.get("sentiment", "neutral"),
                        "message_count": conv_data.get("message_count", len(conv_data.get("visible_messages", []))),
                    }

                    if search_val:
                        if not (
                            search_val in str(chat_entry.get("user_name", "")).lower()
                            or search_val in str(chat_entry.get("phone_number", "")).lower()
                            or search_val in str(chat_entry.get("phone_clean", "")).lower()
                        ):
                            continue

                    chats.append(chat_entry)

                    counters["all"] += 1
                    if state == self.STATE_WAITING_OPERATOR:
                        counters["waiting"] += 1
                    if state == self.STATE_ASSIGNED:
                        counters["with_operator"] += 1
                    if state == self.STATE_BOT_ACTIVE:
                        counters["bot_active"] += 1
                    if state in {self.STATE_RESOLVED, self.STATE_ARCHIVED}:
                        counters["closed"] += 1

            chats.sort(key=lambda c: c.get("last_message_at", ""), reverse=True)

            start = max(0, (max(1, int(page)) - 1) * safe_size)
            paged = chats[start:start + safe_size]
            paged = [self._to_frontend_chat_format(c) for c in paged]
            has_more = len(chats) > start + safe_size
            next_cursor = None
            if has_more:
                last = chats[start:start + safe_size][-1]
                next_cursor = f"{last['last_message_at']}|{last['conversation_id']}"

            return {
                "success": True,
                "chats": paged,
                "total": len(paged),
                "page": page,
                "page_size": safe_size,
                "has_more": has_more,
                "next_cursor": next_cursor,
                "filter": filter_state,
                "counters": counters,
                "search": search,
                "source": "firestore_fallback",
            }
        except Exception as e:
            print(f"⚠️ fallback unified chats failed: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "chats": [], "total": 0, "has_more": False, "error": str(e)}

    async def _fallback_unified_chats_with_timeout(
        self,
        search: str,
        page: int,
        page_size: int,
        filter_state: str,
    ) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._fallback_unified_chats(search, page, page_size, filter_state),
                timeout=self.FALLBACK_UNIFIED_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "chats": [],
                "total": 0,
                "has_more": False,
                "error": "fallback_timeout",
            }
        
    async def get_active_conversations(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Backward-compatible wrapper: return master inbox page 1 (no 6h filter)."""
        try:
            unified = await self.get_unified_chats(search=search or "", page=1, page_size=200)
            return [
                {
                    "conversation_id": c.get("conversation_id"),
                    "user_id": c.get("user_id"),
                    "user_name": c.get("user_name"),
                    "user_phone": c.get("user_phone") or c.get("phone_number"),
                    "phone_clean": c.get("phone_clean"),
                    "last_message": c.get("last_message_text") or ((c.get("last_message") or {}).get("content") if isinstance(c.get("last_message"), dict) else ""),
                    "last_activity": c.get("last_activity") or c.get("last_message_at"),
                    "status": c.get("status") or self._conversation_state_to_status(c.get("conversation_state")),
                    "conversation_state": c.get("conversation_state"),
                    "operator_id": c.get("operator_id"),
                    "unread_count": c.get("unread_count", 0),
                }
                for c in unified.get("chats", [])
            ]
        except Exception as e:
            print(f"❌ Error getting active conversations: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_unified_chats(
        self,
        search: str = "",
        page: int = 1,
        page_size: int = 30,
        filter_state: str = "all",
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        WhatsApp-style inbox driven ONLY by live_chat_index.
        - Single master list ordered by last_message_at desc
        - Optional filter by conversation_state badge
        - Cursor-based pagination (last_message_at + conversation_id)
        - Search by name / phone against index documents
        """
        search_val = (search or "").strip().lower()
        safe_size = max(1, min(int(page_size), 100))
        state_values = self._state_filter_values(filter_state)
        page_num = max(1, int(page))
        can_use_stale_cache = (
            page_num == 1
            and not search_val
            and not cursor
            and not state_values
            and bool(self._unified_chats_cache)
        )
        use_cache_fallback = (
            page_num == 1
            and not search_val
            and not cursor
            and not state_values
            and bool(self._unified_chats_cache)
            and (
                self._unified_chats_cache_page_size is None
                or self._unified_chats_cache_page_size == safe_size
            )
        )
        if use_cache_fallback and self._is_cache_fresh(
            self._unified_chats_cache_time,
            ttl_seconds=self.UNIFIED_CACHE_TTL,
        ):
            print(
                f"[live_chat:unified] source=memory_cache page={page_num} size={safe_size} search={bool(search_val)}"
            )
            return self._cached_unified_response(
                page_num, safe_size, filter_state, search
            )

        try:
            request_started = utc_now()
            db = get_firestore_db()
            if not db:
                if can_use_stale_cache:
                    return self._cached_unified_response(
                        page_num, safe_size, filter_state, search
                    )
                return self._empty_unified_response(
                    page_num,
                    safe_size,
                    filter_state,
                    search,
                    source="firestore_missing",
                )

            index_coll = self._index_collection(db)

            # Build base query (ordered for pagination)
            query = index_coll.order_by("last_message_at", direction=firestore.Query.DESCENDING).order_by("conversation_id")

            if state_values:
                if len(state_values) == 1:
                    query = query.where("conversation_state", "==", state_values[0])
                else:
                    query = query.where("conversation_state", "in", state_values)

            start_after_values = None
            if cursor:
                try:
                    ts_part, conv_part = cursor.split("|", 1)
                    ts_val = self._parse_timestamp(ts_part)
                    start_after_values = [ts_val, conv_part]
                except Exception:
                    start_after_values = None

            fetch_limit = safe_size + 1  # fetch one extra to know if there's more

            def _stream_page(q):
                use_q = q
                if start_after_values:
                    use_q = use_q.start_after(*start_after_values)
                return list(
                    use_q.limit(fetch_limit).stream(
                        timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                        retry=None,
                    )
                )

            docs = await self._run_blocking_with_timeout(
                lambda: _stream_page(query),
                self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
            )
            print(
                f"[live_chat:unified] source=index_page docs={len(docs)} page={page_num} size={safe_size} search={bool(search_val)} filter={filter_state}"
            )

            # If search provided, widen fetch to improve matches (still index-only)
            if search_val:
                widen_limit = min(
                    self.SEARCH_WIDEN_MAX_DOCS,
                    max(fetch_limit * 3, 120),
                )
                def _stream_search(q):
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
                if can_use_stale_cache:
                    return self._cached_unified_response(
                        page_num, safe_size, filter_state, search
                    )
                return self._empty_unified_response(
                    page_num,
                    safe_size,
                    filter_state,
                    search,
                    source="index_empty",
                )

            chats: List[Dict[str, Any]] = []
            for doc in docs:
                data = doc.to_dict() or {}
                state = self._normalize_conversation_state(data)
                customer_info = data.get("customer_info") or {}
                user_id = data.get("user_id")
                user_name = data.get("user_name") or customer_info.get("name") or config.user_names.get(user_id) or "Unknown Customer"
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
                    "last_message_at": last_at.isoformat() if hasattr(last_at, "isoformat") else str(last_at),
                    "conversation_state": state,
                    "operator_id": data.get("operator_id"),
                    "unread_count": data.get("unread_count", 0),
                    "language": data.get("language") or customer_info.get("language") or config.user_data_whatsapp.get(user_id, {}).get("user_preferred_lang", "ar"),
                    "sentiment": data.get("sentiment", "neutral"),
                    "message_count": data.get("message_count", 0),
                }
                chats.append(chat_entry)

            if search_val:
                chats = [
                    c for c in chats
                    if search_val in str(c.get("user_name", "")).lower()
                    or search_val in str(c.get("phone_number", "")).lower()
                    or search_val in str(c.get("phone_clean", "")).lower()
                ]

            # Always order by last_message_at desc (already sorted by query)
            chats.sort(key=lambda c: c.get("last_message_at", ""), reverse=True)

            has_more = len(chats) > safe_size
            paged = chats[:safe_size]
            paged = [self._to_frontend_chat_format(c) for c in paged]
            next_cursor = None
            if has_more:
                last = chats[:safe_size][-1]
                next_cursor = f"{last['last_message_at']}|{last['conversation_id']}"

            total_returned = len(paged)
            if not search_val and not cursor and not state_values:
                self._unified_chats_cache = paged
                self._unified_chats_cache_time = utc_now()
                self._unified_chats_cache_has_more = has_more
                self._unified_chats_cache_total = total_returned
                self._unified_chats_cache_next_cursor = next_cursor
                self._unified_chats_cache_page_size = safe_size

            if page_num == 1 and not cursor:
                counters = await self._compute_index_counters()
            else:
                counters = dict(self._index_counters_cache or self._empty_counters())

            elapsed_ms = int((utc_now() - request_started).total_seconds() * 1000)
            print(
                f"[live_chat:unified] return chats={len(paged)} has_more={has_more} elapsed_ms={elapsed_ms}"
            )

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
            if can_use_stale_cache:
                return self._cached_unified_response(
                    page_num, safe_size, filter_state, search
                )
            return self._empty_unified_response(
                page_num,
                safe_size,
                filter_state,
                search,
                source="index_error",
            )

    async def _compute_index_counters(self) -> Dict[str, int]:
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
                    index_coll.order_by(
                        "last_message_at", direction=firestore.Query.DESCENDING
                    )
                    .limit(self.INDEX_COUNTER_SCAN_LIMIT)
                    .stream(timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS)
                ),
            )
            print(
                f"[live_chat:counters] source=index docs_scanned={len(docs)} limit={self.INDEX_COUNTER_SCAN_LIMIT}"
            )
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

    async def get_history_customers(
        self,
        search: str = "",
        filter_by: str = "all",
        page: int = 1,
        page_size: int = 200,
    ) -> Dict[str, Any]:
        """Canonical customer list for chat history."""
        try:
            users_collection = self._get_users_collection()
            if users_collection is None:
                return {"success": False, "error": "Firestore not initialized"}

            users_docs = await self._stream_user_docs(users_collection)
            user_ids = [doc.id for doc in users_docs]
            fetch_results = await self._stream_conversations_for_users(users_collection, user_ids)

            customers: List[Dict[str, Any]] = []
            for result in fetch_results:
                if isinstance(result, Exception):
                    continue

                user_id, conversations_docs = result

                latest_timestamp = None
                latest_message_text = ""
                latest_customer_info = {}
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

                user_name = (
                    latest_customer_info.get("name")
                    or config.user_names.get(user_id)
                    or ""
                )
                phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=latest_customer_info)
                if not user_name and phone_full and phone_full != "Unknown":
                    user_name = phone_full
                if not user_name:
                    user_name = "Unknown Customer"
                gender = latest_customer_info.get("gender") or config.user_gender.get(user_id, "unknown")

                customers.append({
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
                })

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
                customer for customer in customers
                if self._history_filter_match(
                    self._parse_timestamp(customer.get("last_message_time")),
                    filter_by
                )
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
    ) -> Dict[str, Any]:
        """Canonical conversation list for a single user."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conversations_collection = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

            conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))

            conversations: List[Dict[str, Any]] = []
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

                conversations.append({
                    "id": conv_doc.id,
                    "message_count": message_count,
                    "last_message": last_message,
                    "timestamp": last_timestamp.isoformat(),
                    "user_id": conv_data.get("user_id", user_id),
                    "sentiment": conv_data.get("sentiment", "neutral"),
                    "human_takeover_active": conv_data.get("human_takeover_active", False),
                    "status": conv_data.get("status", "active"),
                })

            if status and status != "all":
                conversations = [conv for conv in conversations if conv.get("status") == status]

            search_value = (search or "").strip().lower()
            if search_value:
                conversations = [
                    conv for conv in conversations
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
            print(f"❌ Error getting history conversations for {user_id}: {e}")
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
    ) -> Dict[str, Any]:
        """Canonical paginated message history for one conversation."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized", "messages": []}

            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            ).document(conversation_id)

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
                normalized_messages.append({
                    **msg,
                    "timestamp": self._parse_timestamp(msg.get("timestamp")).isoformat(),
                })

            search_value = (search or "").strip().lower()
            if search_value:
                normalized_messages = [
                    msg for msg in normalized_messages
                    if search_value in str(msg.get("text", "")).lower()
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
    
    async def get_client_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all conversations for a specific client (for expanded view)
        """
        try:
            db = get_firestore_db()
            if not db:
                return []

            app_id = "linas-ai-bot-backend"
            conversations_collection = db.collection("artifacts").document(app_id).collection(
                "users"
            ).document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

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
                
                conversations.append({
                    "conversation_id": conv_doc.id,
                    "message_count": len(visible_messages),
                    "last_activity": last_message_time.isoformat(),
                    "status": conv_data.get("status", "active"),
                    "sentiment": conv_data.get("sentiment", "neutral"),
                    "human_takeover_active": conv_data.get("human_takeover_active", False),
                    "operator_id": conv_data.get("operator_id")
                })
            
            conversations.sort(key=lambda x: x["last_activity"], reverse=True)
            return conversations
            
        except Exception as e:
            print(f"❌ Error getting client conversations: {e}")
            return []
    
    async def get_waiting_queue(self) -> List[Dict[str, Any]]:
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
            query = (
                index_coll
                .where("conversation_state", "==", self.STATE_WAITING_OPERATOR)
                .order_by("last_message_at", direction=firestore.Query.DESCENDING)
                .limit(300)
            )
            docs = await asyncio.to_thread(
                lambda: list(
                    query.stream(
                        timeout=self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
                        retry=None,
                    )
                )
            )

            if not docs and self.ENABLE_WAITING_QUEUE_FALLBACK_SCAN:
                fallback = await self._fallback_unified_chats("", page=1, page_size=300, filter_state="waiting")
                if fallback.get("success") and fallback.get("chats"):
                    queue = []
                    current_time = utc_now()
                    for chat in fallback.get("chats", []):
                        last_at = self._parse_timestamp(chat.get("last_message_at")) if chat.get("last_message_at") else current_time
                        wait_time_seconds = max(0, int((current_time - last_at).total_seconds()))
                        queue.append({
                            "conversation_id": chat.get("conversation_id"),
                            "user_id": chat.get("user_id"),
                            "user_name": chat.get("user_name"),
                            "user_phone": chat.get("phone_number"),
                            "phone_clean": chat.get("phone_clean"),
                            "language": config.user_data_whatsapp.get(chat.get("user_id"), {}).get("user_preferred_lang", "ar"),
                            "reason": "user_request",
                            "wait_time_seconds": wait_time_seconds,
                            "sentiment": "neutral",
                            "message_count": 0,
                            "priority": 2,
                            "last_message": chat.get("last_message_text", ""),
                        })
                    self._queue_cache = queue
                    self._queue_cache_time = current_time
                    return queue
            elif not docs:
                print("[live_chat:waiting_queue] index empty; fallback scan disabled")

            waiting_queue = []

            for doc in docs:
                data = doc.to_dict() or {}
                data["conversation_id"] = doc.id
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
                user_name = customer_info.get("name") or config.user_names.get(user_id) or "Unknown Customer"
                phone_full = data.get("user_phone") or "Unknown"
                phone_clean = data.get("phone_clean") or "Unknown"
                language = data.get("language") or config.user_data_whatsapp.get(user_id, {}).get("user_preferred_lang", "ar")
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
                    "priority": priority,
                    "last_message": data.get("last_message_text", ""),
                }

                waiting_queue.append(queue_item)
            
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
    
    async def end_conversation(self, conversation_id: str, user_id: str, operator_id: str, adapter=None) -> Dict[str, Any]:
        """
        Mark conversation as resolved/ended
        - Sets status to 'resolved'
        - Records who resolved it and when
        - Removes from active view
        - Sends notification to customer
        - Can be reopened if customer messages again
        """
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                canonical_user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # Update conversation status
            update_data = {
                "status": "resolved",
                "resolved_at": utc_now(),
                "resolved_by": operator_id,
                "human_takeover_active": False,
                "operator_id": None,
                "conversation_state": self.STATE_RESOLVED,
            }
            
            print(f"🔄 Updating conversation {conversation_id} with data: {update_data}")
            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            await asyncio.to_thread(conv_ref.update, update_data)
            print(f"✅ Firebase updated successfully for conversation {conversation_id}")

            # Verify the update
            updated_doc = await asyncio.to_thread(conv_ref.get)
            if updated_doc.exists:
                updated_data = updated_doc.to_dict()
                print(f"✅ Verified: status = {updated_data.get('status')}, resolved_by = {updated_data.get('resolved_by')}")
            
            # Update in-memory state
            config.user_in_human_takeover_mode[canonical_user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Clear current_conversation_id so next message creates a new conversation
            if canonical_user_id in config.user_data_whatsapp:
                config.user_data_whatsapp[canonical_user_id].pop('current_conversation_id', None)
                print(f"🔄 Cleared current_conversation_id for {canonical_user_id} - next message will start new conversation")

            # Invalidate cache
            self.invalidate_cache()

            # Refresh index to reflect resolved state
            await self._refresh_index_for_conversation(canonical_user_id, conversation_id)

            # Send notification to customer
            if adapter:
                try:
                    # Multilingual end conversation messages
                    end_messages = {
                        "ar": "شكراً لتواصلك معنا! تم إنهاء المحادثة. إذا كان لديك أي استفسار آخر، لا تتردد في مراسلتنا مجدداً. 🌟",
                        "en": "Thank you for contacting us! This conversation has been ended. If you have any other questions, feel free to message us again. 🌟",
                        "fr": "Merci de nous avoir contactés! Cette conversation est terminée. Si vous avez d'autres questions, n'hésitez pas à nous écrire à nouveau. 🌟"
                    }
                    
                    # Get user's preferred language from config
                    user_lang = config.user_data_whatsapp.get(canonical_user_id, {}).get('user_preferred_lang', 'ar')
                    notification_message = end_messages.get(user_lang, end_messages['ar'])
                    
                    # Send notification via WhatsApp
                    await adapter.send_text_message(canonical_user_id, notification_message)
                    print(f"✅ Sent end conversation notification to customer {user_id}")
                    
                    # Save notification to Firebase
                    from utils.utils import save_conversation_message_to_firestore
                    await save_conversation_message_to_firestore(
                        user_id=canonical_user_id,
                        role="ai",
                        text=notification_message,
                        conversation_id=conversation_id,
                        metadata={"type": "end_conversation_notification", "operator_id": operator_id}
                    )
                except Exception as e:
                    print(f"⚠️ Failed to send end conversation notification: {e}")
            
            print(f"✅ Conversation {conversation_id} marked as resolved by {operator_id}")
            
            return {
                "success": True,
                "message": "Conversation ended successfully",
                "conversation_id": conversation_id,
                "status": "resolved"
            }
            
        except Exception as e:
            print(f"❌ Error ending conversation: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def reopen_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """
        Reopen a resolved conversation (auto-called when customer messages again)
        """
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                canonical_user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # Reopen conversation - use asyncio.to_thread to prevent blocking
            await asyncio.to_thread(conv_ref.update, {
                "status": "active",
                "reopened_at": utc_now(),
                "resolved_at": None,
                "resolved_by": None,
                "conversation_state": self.STATE_BOT_ACTIVE,
                "human_takeover_active": False,
                "operator_id": None,
            })
            
            print(f"✅ Conversation {conversation_id} reopened (customer messaged again)")

            # Refresh index so UI picks up the reopened state
            await self._refresh_index_for_conversation(canonical_user_id, conversation_id)
            
            return {
                "success": True,
                "message": "Conversation reopened",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"❌ Error reopening conversation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _auto_archive_conversation(self, user_id: str, conversation_id: str):
        """
        Auto-archive conversations older than 6 hours
        """
        try:
            db = get_firestore_db()
            if not db:
                return
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            await asyncio.to_thread(conv_ref.update, {
                "status": "archived",
                "archived_at": utc_now(),
                "archived_reason": "auto_6h_timeout",
                "conversation_state": self.STATE_ARCHIVED,
                "human_takeover_active": False,
                "operator_id": None,
            })

            print(f"📦 Auto-archived conversation {conversation_id} (6-hour timeout)")

            # Refresh index so the archive is reflected in lists
            await self._refresh_index_for_conversation(user_id, conversation_id)
            
        except Exception as e:
            print(f"⚠️ Error auto-archiving conversation: {e}")
    
    async def takeover_conversation(self, conversation_id: str, user_id: str, operator_id: str, operator_name: str = None) -> Dict[str, Any]:
        """Operator takes over a conversation"""
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            resolved_user_id = canonical_user_id
            if db:
                users_coll = db.collection("artifacts").document(self.APP_ID).collection("users")
                conv_ref = users_coll.document(canonical_user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
                conv_snap = await asyncio.to_thread(conv_ref.get)
                if not conv_snap.exists and user_id != canonical_user_id:
                    conv_ref = users_coll.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
                    conv_snap = await asyncio.to_thread(conv_ref.get)
                    if conv_snap.exists:
                        resolved_user_id = user_id
                if not conv_snap.exists:
                    return {"success": False, "error": f"Conversation not found. Check user_id and conversation_id."}
            await set_human_takeover_status(resolved_user_id, conversation_id, True, operator_id, operator_name)
            config.user_in_human_takeover_mode[resolved_user_id] = True
            self.operator_sessions[conversation_id] = operator_id

            # Ensure canonical state is written
            if db:
                await asyncio.to_thread(conv_ref.update, {
                    "conversation_state": self.STATE_ASSIGNED,
                    "last_updated": utc_now(),
                })

            # Refresh index
            await self._refresh_index_for_conversation(resolved_user_id, conversation_id)

            # Invalidate cache
            self.invalidate_cache()

            print(f"✅ Operator {operator_id} took over conversation {conversation_id}")

            return {
                "success": True,
                "message": "Conversation taken over successfully",
                "conversation_id": conversation_id,
                "operator_id": operator_id
            }
            
        except Exception as e:
            print(f"❌ Error taking over conversation: {e}")
            return {"success": False, "error": str(e)}
    
    async def release_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """Release conversation back to bot"""
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            conv_ref = None
            resolved_user_id = canonical_user_id
            if db:
                users_coll = db.collection("artifacts").document(self.APP_ID).collection("users")
                conv_ref = users_coll.document(canonical_user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
                conv_snap = await asyncio.to_thread(conv_ref.get)
                if not conv_snap.exists and user_id != canonical_user_id:
                    conv_ref = users_coll.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
                    conv_snap = await asyncio.to_thread(conv_ref.get)
                    if conv_snap.exists:
                        resolved_user_id = user_id
                if not conv_snap.exists:
                    return {
                        "success": False,
                        "error": f"Conversation not found. Check user_id and conversation_id.",
                    }
            await set_human_takeover_status(resolved_user_id, conversation_id, False)
            config.user_in_human_takeover_mode[resolved_user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Ensure canonical state is written
            if db:
                await asyncio.to_thread(conv_ref.update, {
                    "conversation_state": self.STATE_BOT_ACTIVE,
                    "last_updated": utc_now(),
                    "operator_id": None,
                })

            # Refresh index
            await self._refresh_index_for_conversation(resolved_user_id, conversation_id)

            # Invalidate cache
            self.invalidate_cache()

            print(f"✅ Conversation {conversation_id} released back to bot")

            return {
                "success": True,
                "message": "Conversation released to bot successfully",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"❌ Error releasing conversation: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_operator_message(
        self, conversation_id: str, user_id: str, message: str, operator_id: str, adapter, message_type: str = "text"
    ) -> Dict[str, Any]:
        """Send message from operator to customer
        
        Args:
            conversation_id: The conversation ID
            user_id: The customer's user ID (room_id for Qiscus)
            message: Message content (text for text, base64 for voice/image)
            operator_id: The operator's ID
            adapter: WhatsApp adapter instance
            message_type: Type of message - "text", "voice", or "image"
        """
        try:
            from utils.utils import save_conversation_message_to_firestore, get_firestore_db
            from utils.utils import get_canonical_user_id_and_phone
            
            canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id)
            # For Qiscus, we need to fetch the phone_number from Firebase
            phone_number = None
            db = get_firestore_db()
            if db:
                try:
                    app_id = "linas-ai-bot-backend"
                    user_doc = db.collection("artifacts").document(app_id).collection("users").document(canonical_user_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        phone_number = user_data.get("phone_full")
                        print(f"📱 Found phone_number from Firebase: {phone_number}")
                except Exception as e:
                    print(f"⚠️ Could not fetch phone_number from Firebase: {e}")
            
            # Handle different message types
            if message_type == "voice":
                # message contains base64 audio data
                
                print(f"🎙️ Operator {operator_id} recorded voice message for {user_id}")
                
                # Step 0: Convert WebM to Opus (Qiscus/WhatsApp standard)
                print(f"� Converting voice to Opus format (WhatsApp standard)...")
                audio_data_to_upload = message
                upload_file_name = f"voice_{user_id}_{int(__import__('time').time())}.webm"
                upload_file_type = "audio/webm"
                
                try:
                    from utils.utils import convert_webm_to_opus
                    opus_data, opus_file_name = convert_webm_to_opus(message)
                    if opus_file_name:  # Conversion successful
                        audio_data_to_upload = opus_data
                        upload_file_name = opus_file_name
                        upload_file_type = "audio/ogg"
                        print(f"✅ Voice converted to OGG/Opus")
                except Exception as e:
                    print(f"⚠️ WebM to Opus conversion failed: {e}")
                    print(f"   Continuing with original WebM format...")
                
                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage
                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=audio_data_to_upload,
                        file_name=upload_file_name,
                        file_type=upload_file_type
                    )
                    print(f"✅ Voice uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    if "404" in str(e) and "bucket does not exist" in str(e).lower():
                        print(f"   📌 HINT: Check storageBucket in data/firebase_data.json")
                        print(f"   📌 Actual bucket: linas-ai-bot.firebasestorage.app (not appspot.com)")
                    storage_url = None
                
                # Step 2: Save to Firebase Firestore
                print(f"📝 Saving voice metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text="[Voice Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "voice",
                        "audio_url": storage_url,  # Store the public URL with key name 'audio_url' for easy retrieval
                        "audio_mime_type": upload_file_type,
                        "message_length": len(message)
                    }
                )
                
                # Step 3: Send voice message via WhatsApp
                print(f"🎙️ Sending voice message via WhatsApp to {user_id}...")
                try:
                    if storage_url:
                        whatsapp_audio_url = build_whatsapp_audio_delivery_url(storage_url)
                        print(f"📤 Proxy URL for WhatsApp: {whatsapp_audio_url}")
                        send_result = await adapter.send_audio_message(canonical_user_id, whatsapp_audio_url)
                        if send_result.get("success"):
                            print(f"✅ Sent voice message via WhatsApp")
                        else:
                            error_msg = send_result.get("error", "Unknown error")
                            print(f"⚠️ WhatsApp audio send failed: {error_msg}")
                            print(f"⚠️ Audio URL was: {storage_url}")
                            return {
                                "success": False,
                                "error": f"WhatsApp audio send failed: {error_msg}",
                                "storage_url": storage_url,
                                "whatsapp_audio_url": whatsapp_audio_url
                            }
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام رسالة صوتية من المشغل. يرجى فتح لوحة المعلومات لسماعها."
                        await adapter.send_text_message(canonical_user_id, text_notification)
                        print(f"✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via WhatsApp: {e}")
                    import traceback
                    traceback.print_exc()
                    return {"success": False, "error": f"Failed to send voice: {str(e)}"}

                print(f"✅ Voice message processed and sent for {user_id}")

                return {
                    "success": True,
                    "message": "Voice message sent successfully",
                    "storage_url": storage_url,
                    "whatsapp_audio_url": build_whatsapp_audio_delivery_url(storage_url) if storage_url else None
                }
                    
            elif message_type == "image":
                # message contains base64 image data
                print(f"🖼️ Operator {operator_id} uploaded image for {user_id}")
                print(f"📝 Uploading image to Firebase Storage...")
                
                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage
                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=message,
                        file_name=f"image_{user_id}_{int(__import__('time').time())}.jpg",
                        file_type="image/jpeg"
                    )
                    print(f"✅ Image uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    storage_url = None
                
                # Step 2: Save to Firebase Firestore
                print(f"📝 Saving image metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text="[Image Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "image",
                        "image_data": message,  # Store full base64 as backup
                        "image_url": storage_url,  # Store the public URL with key name 'image_url' for easy retrieval
                        "message_length": len(message)
                    }
                )
                
                # Step 3: Send image via Qiscus
                print(f"🖼️ Sending image via Qiscus to {user_id}...")
                try:
                    if storage_url:
                        # Send as native image message (displays in gallery on phone, not just a link)
                        await adapter.send_image_message(canonical_user_id, storage_url, caption="صورة من المشغل")
                        print(f"✅ Sent image as native image message via Qiscus")
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام صورة من المشغل. يرجى فتح لوحة المعلومات لعرضها."
                        await adapter.send_text_message(canonical_user_id, text_notification)
                        print(f"✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via Qiscus: {e}")
                    import traceback
                    traceback.print_exc()
                
                print(f"✅ Image message processed and sent for {user_id}")
                
                return {"success": True, "message": "Image message sent successfully", "storage_url": storage_url}
                    
            else:  # Default to text
                # Save to Firestore first (SSE broadcasts immediately → message appears in UI fast)
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text=message,
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={"operator_id": operator_id, "handled_by": "human"}
                )
                print(f"✅ Saved operator message to Firestore")

                # Send via WhatsApp in background - return immediately so UI feels fast
                async def _send_whatsapp():
                    try:
                        result = await adapter.send_text_message(canonical_user_id, message)
                        if result.get("success"):
                            print(f"✅ Operator {operator_id} sent message to {user_id} via WhatsApp")
                        else:
                            print(f"⚠️ WhatsApp send failed but message saved: {result.get('error')}")
                    except Exception as send_error:
                        print(f"⚠️ WhatsApp adapter error but message saved: {send_error}")

                asyncio.create_task(_send_whatsapp())
                return {"success": True, "message": "Message sent successfully"}
            
        except Exception as e:
            print(f"❌ Error sending operator message: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def update_operator_status(self, operator_id: str, status: str) -> Dict[str, Any]:
        """Update operator availability"""
        try:
            valid_statuses = ["available", "busy", "away"]
            if status not in valid_statuses:
                return {"success": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}
            
            self.operator_status[operator_id] = status
            print(f"✅ Operator {operator_id} status: {status}")
            
            return {"success": True, "operator_id": operator_id, "status": status}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_conversation_details(
        self,
        user_id: str,
        conversation_id: str,
        max_messages: int = 100,
        days: int = 0,
        before: Optional[str] = None,
        day_window: int = 0,
    ) -> Dict[str, Any]:
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
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            index_coll = self._index_collection(db)

            # Fast path: initial open (no days/before filter) — serve from index in <3s so UI opens in <5s
            if days <= 0 and not before:
                try:
                    index_ref = index_coll.document(conversation_id)
                    index_doc = await self._get_doc_with_timeout(index_ref, timeout_seconds=self.INDEX_READ_TIMEOUT_SECONDS)
                    if index_doc.exists:
                        data = index_doc.to_dict() or {}
                        recent = data.get("recent_messages")
                        if isinstance(recent, list) and len(recent) > 0:
                            msg_count = int(data.get("message_count") or 0)
                            print(
                                f"[live_chat:conversation] source=index_recent conv={conversation_id} returned={len(recent)} total={msg_count}"
                            )
                            return {
                                "success": True,
                                "conversation_id": conversation_id,
                                "messages": recent,
                                "total_messages": msg_count,
                                "returned_messages": len(recent),
                                "has_more": msg_count > len(recent),
                                "sentiment": str(data.get("sentiment") or "neutral"),
                                "status": self._conversation_state_to_status(data.get("conversation_state")),
                            }
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass

            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            candidate_user_ids = [canonical_user_id]
            if user_id != canonical_user_id:
                candidate_user_ids.append(user_id)

            conv_doc = None
            effective_user_id = canonical_user_id
            had_timeout = False
            for candidate_user_id in candidate_user_ids:
                candidate_ref = (
                    db.collection("artifacts")
                    .document(app_id)
                    .collection("users")
                    .document(candidate_user_id)
                    .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                    .document(conversation_id)
                )
                try:
                    candidate_doc = await self._get_doc_with_timeout(candidate_ref)
                except asyncio.TimeoutError:
                    had_timeout = True
                    continue
                if candidate_doc.exists:
                    conv_doc = candidate_doc
                    effective_user_id = candidate_user_id
                    break
                conv_doc = candidate_doc

            if not conv_doc or not conv_doc.exists:
                if had_timeout:
                    return {
                        "success": False,
                        "error": "Conversation loading timed out. Please retry.",
                    }
                return {"success": False, "error": "Conversation not found"}

            payload = conv_doc.to_dict() or {}
            raw_messages = list(payload.get("messages") or [])
            total_messages = len(raw_messages)
            sentiment = str(payload.get("sentiment") or "neutral")
            status = str(payload.get("status") or "active")

            # Fast path for initial open (days=0, before not set):
            # avoid scanning/normalizing the full conversation history on every open.
            if days <= 0 and not before:
                tail_window = max(max_messages * 4, 200)
                candidate = raw_messages[-tail_window:] if len(raw_messages) > tail_window else raw_messages
                messages = self._visible_chat_messages(candidate)
                messages.sort(key=lambda m: self._parse_timestamp(m.get("timestamp")))
                messages_before_slice = len(messages)
                if len(messages) > max_messages:
                    messages = messages[-max_messages:]
            else:
                messages = self._visible_chat_messages(raw_messages)
                now = utc_now()
                cutoff = now - datetime.timedelta(days=days) if days > 0 else None
                before_dt = self._parse_timestamp(before) if before else None
                # When before + day_window: only messages in (before_dt - day_window days, before_dt]
                after_dt = (before_dt - datetime.timedelta(days=day_window)) if (before_dt and day_window > 0) else None

                filtered = []
                for msg in messages:
                    ts = self._parse_timestamp(msg.get("timestamp"))
                    if days > 0 and ts < cutoff:
                        continue
                    if before_dt and ts >= before_dt:
                        continue
                    if after_dt is not None and ts <= after_dt:
                        continue
                    filtered.append(msg)
                messages = filtered
                messages.sort(key=lambda m: self._parse_timestamp(m.get("timestamp")))
                messages_before_slice = len(messages)
                if len(messages) > max_messages:
                    messages = messages[-max_messages:]

            formatted_messages = [self._format_single_message(msg) for msg in messages]

            # WhatsApp-style: has_more = more older messages available (for Load More)
            has_more = (
                messages_before_slice > max_messages if before
                else total_messages > max_messages
            )

            out = {
                "success": True,
                "conversation_id": conversation_id,
                "messages": formatted_messages,
                "total_messages": total_messages,
                "returned_messages": len(formatted_messages),
                "has_more": has_more,
                "sentiment": sentiment,
                "status": status
            }
            print(
                f"[live_chat:conversation] source=full_document conv={conversation_id} total_raw={total_messages} returned={len(formatted_messages)}"
            )
            # Optional read-path backfill (disabled by default to avoid write amplification)
            if (
                days <= 0
                and not before
                and self.ENABLE_INDEX_BACKFILL_ON_READ
                and self._should_schedule_read_path_refresh(conversation_id)
            ):
                asyncio.create_task(
                    self._refresh_index_for_conversation(
                        effective_user_id, conversation_id
                    )
                )
            # #region agent log
            try:
                import json
                import os
                _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                _logpath = os.path.join(_root, ".cursor", "debug-420609.log")
                os.makedirs(os.path.dirname(_logpath), exist_ok=True)
                first_ts = formatted_messages[0]["timestamp"] if formatted_messages else None
                last_ts = formatted_messages[-1]["timestamp"] if formatted_messages else None
                with open(_logpath, "a") as f:
                    f.write(json.dumps({"sessionId":"420609","location":"live_chat_service:get_conversation_details","message":"service return","data":{"msg_count":len(formatted_messages),"first_ts":first_ts,"last_ts":last_ts},"timestamp":int(__import__("time").time()*1000),"hypothesisId":"H1,H9"}) + "\n")
            except Exception:
                pass
            # #endregion
            return out

        except Exception as e:
            print(f"❌ Error getting conversation details: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def get_faq_match_context(
        self, user_id: str, conversation_id: str, message_id: str
    ) -> Dict[str, Any]:
        """
        Get faq_match metadata and current FAQ entry for a message (for FAQ correction modal).
        Returns faq_match from message metadata and current_entry (question, answer) if faq_id exists.
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)

            conv_doc = await asyncio.to_thread(conv_ref.get)
            if not conv_doc.exists:
                return {"success": False, "error": "Conversation not found"}

            doc_data = conv_doc.to_dict() or {}
            messages = doc_data.get("messages", [])
            message_id_str = str(message_id).strip()

            def _msg_id(m: Dict[str, Any]) -> str:
                mid = m.get("message_id")
                if mid:
                    return str(mid).strip()
                meta = (m.get("metadata") or {})
                for key in ("message_id", "source_message_id"):
                    if meta.get(key):
                        return str(meta[key]).strip()
                return ""

            faq_match = None
            for msg in messages:
                if _msg_id(msg) == message_id_str:
                    meta = msg.get("metadata") or {}
                    faq_match = meta.get("faq_match")
                    break

            if not faq_match:
                return {
                    "success": True,
                    "faq_match": None,
                    "current_entry": None,
                    "message": "No FAQ match for this message",
                }

            faq_id = faq_match.get("faq_id")
            current_entry = None
            if faq_id is not None:
                try:
                    from modules.local_qa_api import read_qa_pairs
                    qa_pairs = read_qa_pairs()
                    idx = (int(faq_id) - 1) if isinstance(faq_id, int) else (int(faq_id) - 1 if isinstance(faq_id, str) and faq_id.isdigit() else -1)
                    if 0 <= idx < len(qa_pairs):
                        row = qa_pairs[idx]
                        current_entry = {
                            "question": row.get("question", ""),
                            "answer": row.get("answer", ""),
                            "language": row.get("language", "ar"),
                            "qa_group_id": row.get("qa_group_id"),
                        }
                except Exception as e:
                    print(f"⚠️ get_faq_match_context read_qa_pairs: {e}")

            return {
                "success": True,
                "faq_match": faq_match,
                "current_entry": current_entry,
            }
        except Exception as e:
            print(f"❌ Error in get_faq_match_context: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def update_message_content(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        new_content: str,
    ) -> Dict[str, Any]:
        """
        Update a single message's text in a conversation (e.g. operator edit after dislike).
        Updates Firestore, invalidates cache, and broadcasts message_updated for real-time UI.
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)

            conv_doc = await asyncio.to_thread(conv_ref.get)
            if not conv_doc.exists:
                return {"success": False, "error": "Conversation not found"}

            doc_data = conv_doc.to_dict() or {}
            messages = list(doc_data.get("messages", []))
            message_id_str = str(message_id).strip()
            if not message_id_str:
                return {"success": False, "error": "message_id is required"}

            def _msg_id(m: Dict[str, Any]) -> str:
                mid = m.get("message_id")
                if mid:
                    return str(mid).strip()
                meta = (m.get("metadata") or {})
                for key in ("message_id", "source_message_id"):
                    if meta.get(key):
                        return str(meta[key]).strip()
                return ""

            found_index = None
            for i, msg in enumerate(messages):
                if _msg_id(msg) == message_id_str:
                    found_index = i
                    break

            if found_index is None:
                return {"success": False, "error": "Message not found"}

            new_text = (new_content or "").strip()
            if not new_text:
                return {"success": False, "error": "new_content cannot be empty"}

            messages[found_index]["text"] = new_text
            meta = messages[found_index].get("metadata") or {}
            meta["edited_at"] = utc_now().isoformat()
            messages[found_index]["metadata"] = meta

            await asyncio.to_thread(conv_ref.update, {
                "messages": messages,
                "last_updated": utc_now(),
            })
            self.invalidate_cache()

            updated_msg = messages[found_index]
            dash_msg = {
                "message_id": message_id_str,
                "content": new_text,
                "text": new_text,
                "timestamp": updated_msg.get("timestamp"),
                "is_user": updated_msg.get("role") == "user",
                "handled_by": (updated_msg.get("metadata") or {}).get("handled_by") or updated_msg.get("handled_by") or "bot",
                "role": updated_msg.get("role"),
            }

            try:
                from modules.live_chat_api import broadcast_sse_event
                asyncio.create_task(broadcast_sse_event("message_updated", {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id_str,
                    "message": dash_msg,
                }))
            except Exception as sse_err:
                print(f"⚠️ SSE broadcast after edit failed: {sse_err}")

            return {
                "success": True,
                "conversation_id": conversation_id,
                "message_id": message_id_str,
                "message": dash_msg,
            }
        except Exception as e:
            print(f"❌ Error updating message content: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics"""
        try:
            active_conversations = await self.get_active_conversations()
            waiting_queue = await self.get_waiting_queue()
            
            total_active = len(active_conversations)
            bot_handling = len([c for c in active_conversations if c["status"] == "bot"])
            human_handling = len([c for c in active_conversations if c["status"] == "human"])
            waiting_human = len(waiting_queue)
            
            sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
            for conv in active_conversations:
                sentiment = conv.get("sentiment", "neutral")
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
            
            avg_wait_time = 0
            if waiting_queue:
                total_wait = sum(item["wait_time_seconds"] for item in waiting_queue)
                avg_wait_time = total_wait / len(waiting_queue)
            
            return {
                "success": True,
                "metrics": {
                    "total_active_conversations": total_active,
                    "bot_handling": bot_handling,
                    "human_handling": human_handling,
                    "waiting_for_human": waiting_human,
                    "sentiment_distribution": sentiment_counts,
                    "average_wait_time_seconds": int(avg_wait_time),
                    "active_operators": len([op for op, status in self.operator_status.items() if status == "available"]),
                    "time_window_hours": 6
                },
                "timestamp": utc_now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error getting metrics: {e}")
            return {"success": False, "error": str(e)}

    def _normalize_phone_digits(self, value: Any) -> str:
        """Return digits-only phone value (supports +, spaces, dashes, 00 prefix)."""
        if value is None:
            return ""
        digits = re.sub(r"\D", "", str(value))
        if digits.startswith("00"):
            digits = digits[2:]
        return digits

    def _build_phone_variants(self, value: Any) -> set:
        """
        Build comparable phone variants to support mixed country-code/local searches.
        Example: +96176466674 -> {96176466674, 76466674, 6466674}
        """
        digits = self._normalize_phone_digits(value)
        if not digits:
            return set()

        variants = {digits}

        if digits.startswith("0") and len(digits) > 1:
            variants.add(digits[1:])

        # Lebanon-aware variants
        if digits.startswith("961") and len(digits) > 3:
            local_number = digits[3:]
            variants.add(local_number)
            if local_number.startswith("0") and len(local_number) > 1:
                variants.add(local_number[1:])
        elif len(digits) == 8:
            variants.add(f"961{digits}")
            if digits.startswith("0") and len(digits) > 1:
                variants.add(f"961{digits[1:]}")

        # Generic "local-part" fallback for other country codes.
        if len(digits) > 8:
            variants.add(digits[-8:])
        if len(digits) > 7:
            variants.add(digits[-7:])

        return {variant for variant in variants if len(variant) >= 2}

    def _phone_matches_search(self, search_term: str, *candidate_values: Any) -> bool:
        """Return True when normalized phone variants partially overlap."""
        search_variants = self._build_phone_variants(search_term)
        if not search_variants:
            return False

        for candidate_value in candidate_values:
            candidate_variants = self._build_phone_variants(candidate_value)
            for search_variant in search_variants:
                for candidate_variant in candidate_variants:
                    if search_variant in candidate_variant or candidate_variant in search_variant:
                        return True
        return False

    def _filter_conversations(self, conversations: List[Dict[str, Any]], search_term: str) -> List[Dict[str, Any]]:
        """Filter conversations by client name and/or phone (partial, normalized)."""
        normalized_search = (search_term or "").strip()
        if not normalized_search:
            return conversations

        lowered_search = normalized_search.lower()
        has_phone_digits = bool(self._normalize_phone_digits(normalized_search))

        filtered = []
        for conversation in conversations:
            user_name = str(conversation.get("user_name", "")).lower()
            if lowered_search in user_name:
                filtered.append(conversation)
                continue

            phone_candidates = [
                conversation.get("user_phone"),
                conversation.get("phone_clean"),
            ]
            user_id = conversation.get("user_id")
            user_id_digits = self._normalize_phone_digits(user_id)
            resolved_phone_digits = self._normalize_phone_digits(conversation.get("user_phone"))

            # Only consider user_id as phone fallback when no better phone is available.
            if user_id_digits and (not resolved_phone_digits or resolved_phone_digits == user_id_digits):
                phone_candidates.append(user_id)

            if has_phone_digits and self._phone_matches_search(
                normalized_search,
                *phone_candidates,
            ):
                filtered.append(conversation)

        return filtered

    def _choose_preferred_phone(self, current_phone: Optional[str], candidate_phone: str) -> str:
        """Prefer a richer display phone (with +country code / longer digits)."""
        if not current_phone:
            return candidate_phone

        current_digits = self._normalize_phone_digits(current_phone)
        candidate_digits = self._normalize_phone_digits(candidate_phone)

        if candidate_phone.startswith("+") and not current_phone.startswith("+"):
            return candidate_phone
        if len(candidate_digits) > len(current_digits):
            return candidate_phone

        return current_phone

    def _load_phone_room_mapping(self) -> Dict[str, str]:
        """Load `data/phone_to_room_mapping.json` with short TTL cache."""
        now = utc_now()
        if (
            self._phone_mapping_cache_time is not None
            and (now - self._phone_mapping_cache_time).total_seconds() < self.PHONE_MAPPING_CACHE_TTL
        ):
            return self._room_to_phone_cache

        phone_to_room = {}
        room_to_phone = {}

        mapping_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "phone_to_room_mapping.json",
        )

        try:
            with open(mapping_path, "r", encoding="utf-8") as mapping_file:
                mapping_data = json.load(mapping_file)
            raw_mapping = mapping_data.get("phone_to_room_mapping", {})
            if isinstance(raw_mapping, dict):
                for raw_phone, raw_room_id in raw_mapping.items():
                    room_id = str(raw_room_id).strip()
                    phone_value = str(raw_phone).strip()
                    normalized_phone = self._normalize_phone_digits(phone_value)

                    if not room_id or not normalized_phone:
                        continue

                    phone_to_room[normalized_phone] = room_id
                    room_to_phone[room_id] = self._choose_preferred_phone(
                        room_to_phone.get(room_id),
                        phone_value
                    )
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"⚠️ Failed to load phone_to_room_mapping.json: {e}")

        self._phone_to_room_cache = phone_to_room
        self._room_to_phone_cache = room_to_phone
        self._phone_mapping_cache_time = now
        return self._room_to_phone_cache

    def _get_mapped_phone_for_room(self, user_id: str) -> Optional[str]:
        """Return mapped phone for a room_id/user_id when available."""
        room_to_phone = self._load_phone_room_mapping()
        return room_to_phone.get(str(user_id))

    def _resolve_user_phone(self, user_id: str, customer_info: Optional[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Resolve best phone for dashboard/search:
        1) customer_info
        2) runtime memory (config.user_data_whatsapp)
        3) static phone_to_room_mapping.json
        """
        customer_info = customer_info or {}
        user_data = config.user_data_whatsapp.get(user_id, {})

        phone_full = str(customer_info.get("phone_full") or "").strip()
        phone_clean_raw = str(customer_info.get("phone_clean") or "").strip()
        memory_phone = str(user_data.get("phone_number") or "").strip()
        mapped_phone = str(self._get_mapped_phone_for_room(user_id) or "").strip()

        user_digits = self._normalize_phone_digits(user_id)
        phone_full_digits = self._normalize_phone_digits(phone_full)
        memory_digits = self._normalize_phone_digits(memory_phone)
        mapped_digits = self._normalize_phone_digits(mapped_phone)

        # If Firestore saved room_id instead of real phone, replace it.
        if phone_full_digits and user_digits and phone_full_digits == user_digits:
            if mapped_digits and mapped_digits != user_digits:
                phone_full = mapped_phone
                phone_full_digits = mapped_digits
            elif memory_digits and memory_digits != user_digits:
                phone_full = memory_phone
                phone_full_digits = memory_digits

        # If still missing, fallback to memory then static mapping.
        if not phone_full_digits:
            if memory_digits:
                phone_full = memory_phone
                phone_full_digits = memory_digits
            elif mapped_digits:
                phone_full = mapped_phone
                phone_full_digits = mapped_digits

        clean_digits = self._normalize_phone_digits(phone_clean_raw)
        if clean_digits and user_digits and clean_digits == user_digits and phone_full_digits:
            clean_digits = phone_full_digits
        if not clean_digits:
            clean_digits = phone_full_digits

        # Prefer E.164 for display (single canonical format everywhere)
        if phone_full:
            e164 = normalize_phone(phone_full)
            if e164:
                phone_full = e164
        elif clean_digits and len(clean_digits) >= 10:
            e164 = normalize_phone("+" + clean_digits if clean_digits.startswith("961") else "961" + clean_digits)
            if e164:
                phone_full = e164
        # Backward-compatible "clean" format used elsewhere in the app.
        if clean_digits.startswith("961") and len(clean_digits) > 8:
            phone_clean = clean_digits[3:]
        else:
            phone_clean = clean_digits

        if not phone_full:
            phone_full = "Unknown"
        if not phone_clean:
            phone_clean = "Unknown"

        return phone_full, phone_clean
    
    def _parse_timestamp(self, timestamp) -> datetime.datetime:
        """Parse various timestamp formats - always returns UTC-aware datetime"""
        return parse_timestamp_utc(timestamp)


# Global instance
live_chat_service = LiveChatService()
