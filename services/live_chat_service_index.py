from __future__ import annotations

import asyncio
import datetime
import json
import os
from typing import Any

from google.cloud import firestore

import config
from services.live_chat_channel import coerce_live_chat_user_id, resolve_live_chat_channel
from services.live_chat_contracts import (
    parse_timestamp_utc,
    utc_now,
)
from utils.utils import (
    get_canonical_user_id_and_phone,
)


class LiveChatIndexMixin:
    """Index, cache, and conversation-state helpers."""

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

    ACTIVE_TIME_WINDOW: Any
    APP_ID: Any
    FIRESTORE_DOC_TIMEOUT_SECONDS: Any
    FIRESTORE_QUERY_TIMEOUT_SECONDS: Any
    INDEX_COLLECTION: Any
    INDEX_REFRESH_MIN_INTERVAL_SECONDS: Any
    INDEX_WRITE_COOLDOWN_SECONDS: Any
    PERSIST_UNIFIED_CACHE: Any
    STATE_ARCHIVED: Any
    STATE_ASSIGNED: Any
    STATE_BOT_ACTIVE: Any
    STATE_RESOLVED: Any
    STATE_WAITING_OPERATOR: Any
    UNIFIED_CACHE_PATH: Any
    UNIFIED_DISK_CACHE_MAX_AGE_SECONDS: Any
    _parse_timestamp: Any
    _read_path_refresh_tracker: Any

    def _normalize_conversation_state(self, conv_data: dict) -> Any:
        """
        Resolve a safe canonical conversation_state without downgrading valid states.
        human_takeover_active explicitly False means released to bot — never trust stale
        conversation_state waiting/assigned (common after release when index/doc briefly disagree).
        """
        data = conv_data or {}
        state = data.get("conversation_state")
        status = str(data.get("status", "")).lower()
        resolved_at = data.get("resolved_at")
        archived_at = data.get("archived_at")
        hta_raw = data.get("human_takeover_active")
        operator_id = data.get("operator_id")
        valid_states = {
            self.STATE_BOT_ACTIVE,
            self.STATE_WAITING_OPERATOR,
            self.STATE_ASSIGNED,
            self.STATE_RESOLVED,
            self.STATE_ARCHIVED,
        }

        if archived_at or status == "archived":
            return self.STATE_ARCHIVED
        if resolved_at or status in {"resolved", "closed"}:
            return self.STATE_RESOLVED

        # Release cooldown on the doc: never classify as waiting from stale status/state (fallback scanner, etc.)
        try:
            raw_sup = data.get("post_release_escalation_suppressed_until")
            if raw_sup is not None:
                sup_until = parse_timestamp_utc(raw_sup)
                if sup_until and sup_until > utc_now():
                    if hta_raw is not True:
                        return self.STATE_BOT_ACTIVE
        except Exception:
            pass

        # Explicit False: released — stale waiting_for_operator on source or live_chat_index must not win
        if hta_raw is False:
            if state in (self.STATE_WAITING_OPERATOR, self.STATE_ASSIGNED):
                return self.STATE_BOT_ACTIVE
            if state in valid_states:
                return str(state)
            if status in {"waiting", "waiting_for_operator", "pending", "waiting_human"}:
                return self.STATE_BOT_ACTIVE
            return self.STATE_BOT_ACTIVE

        if hta_raw is True:
            return self.STATE_ASSIGNED if operator_id else self.STATE_WAITING_OPERATOR

        # Legacy: human_takeover_active field absent — keep old behavior (trust conversation_state if set)
        if state in valid_states:
            return str(state)

        human_takeover = bool(data.get("human_takeover_active", False))
        if human_takeover:
            return self.STATE_ASSIGNED if operator_id else self.STATE_WAITING_OPERATOR
        if status in {"waiting", "waiting_for_operator", "pending", "waiting_human"}:
            return self.STATE_WAITING_OPERATOR

        return self.STATE_BOT_ACTIVE

    def _is_live_window(self, ts: datetime.datetime) -> Any:
        return bool(ts) and (utc_now() - ts).total_seconds() <= self.ACTIVE_TIME_WINDOW

    def _index_recency_query(self, index_coll: Any) -> Any:
        """Order inbox rows by recency using Firestore's automatic single-field index."""
        return index_coll.order_by("last_message_at", direction=firestore.Query.DESCENDING)

    def _state_filter_values(self, filter_key: str) -> Any:
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

    def _conversation_state_to_status(self, state: str) -> Any:
        """Map canonical conversation_state to frontend status (bot, waiting_human, human)."""
        if state == self.STATE_ASSIGNED:
            return "human"
        if state == self.STATE_WAITING_OPERATOR:
            return "waiting_human"
        if state in {self.STATE_RESOLVED, self.STATE_ARCHIVED}:
            return "closed"
        return "bot"

    def _to_frontend_chat_format(self, chat: dict[str, Any]) -> dict[str, Any]:
        """Enrich chat entry with frontend-expected fields (status, last_message, user_phone, last_activity)."""
        state = chat.get("conversation_state", self.STATE_BOT_ACTIVE)
        last_text = chat.get("last_message_text", "")
        last_at = chat.get("last_message_at", "")
        if last_at is not None and hasattr(last_at, "isoformat") and not isinstance(last_at, str):
            last_at = last_at.isoformat()
        else:
            last_at = str(last_at or "")
        out = dict(chat)
        conv_id = str(chat.get("conversation_id") or "").strip()
        out["conversation_id"] = conv_id
        out["user_id"] = coerce_live_chat_user_id(out, conversation_id=conv_id)
        out["status"] = self._conversation_state_to_status(state)
        out["user_phone"] = chat.get("user_phone") or chat.get("phone_number", "")
        out["last_activity"] = last_at
        out["last_message_at"] = last_at
        out["last_message"] = (
            {"content": str(last_text or ""), "timestamp": last_at, "is_user": False} if last_text or last_at else None
        )
        out["channel"] = resolve_live_chat_channel(out.get("user_id"), out)
        return out

    def _index_collection(self, db: Any) -> Any:
        return db.collection("artifacts").document(self.APP_ID).collection(self.INDEX_COLLECTION)

    def _build_firestore_user_candidates(self, user_id: str) -> list[str]:
        """
        Build ordered candidate user IDs for Firestore document lookup.
        Handles canonical/raw IDs and +prefix variants.
        """
        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
        candidates: list[str] = []

        def _add(candidate: str) -> None:
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        def _add_alt_phone_variant(candidate: str) -> None:
            if not candidate:
                return
            if candidate.startswith("+") or (candidate.isdigit() and len(candidate) >= 10):
                alt = candidate[1:] if candidate.startswith("+") else f"+{candidate}"
                _add(alt)

        _add(user_id)
        _add(canonical_user_id)
        _add_alt_phone_variant(user_id)
        _add_alt_phone_variant(canonical_user_id)
        return candidates

    async def _resolve_conversation_doc_ref(self, db: Any, user_id: str, conversation_id: str) -> Any:
        """
        Resolve a conversation document by trying candidate Firestore user IDs.
        Returns (conv_ref, conv_snap, resolved_user_id).
        """
        users_coll = db.collection("artifacts").document(self.APP_ID).collection("users")
        last_ref = None
        last_snap = None

        for candidate_user_id in self._build_firestore_user_candidates(user_id):
            candidate_ref = (
                users_coll.document(candidate_user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )
            candidate_snap = await self._get_doc_with_timeout(
                candidate_ref,
                timeout_seconds=self.FIRESTORE_QUERY_TIMEOUT_SECONDS,
            )
            last_ref = candidate_ref
            last_snap = candidate_snap
            if candidate_snap.exists:
                return candidate_ref, candidate_snap, candidate_user_id

        return last_ref, last_snap, user_id

    def _empty_counters(self) -> dict[str, int]:
        return {
            "all": 0,
            "waiting": 0,
            "with_operator": 0,
            "bot_active": 0,
            "closed": 0,
        }

    def _is_index_write_paused(self) -> Any:
        if self._index_write_paused_until is None:
            return False
        return utc_now() < self._index_write_paused_until

    def _pause_index_writes(self, reason: str) -> None:
        self._index_write_paused_until = utc_now() + datetime.timedelta(seconds=self.INDEX_WRITE_COOLDOWN_SECONDS)
        print(f"⚠️ Pausing live_chat_index writes for {self.INDEX_WRITE_COOLDOWN_SECONDS}s: {reason}")

    def _should_schedule_read_path_refresh(self, conversation_id: str) -> Any:
        now = utc_now()
        last = self._read_path_refresh_tracker.get(conversation_id)
        if last:
            elapsed = (now - last).total_seconds()
            if elapsed < self.INDEX_REFRESH_MIN_INTERVAL_SECONDS:
                return False
        self._read_path_refresh_tracker[conversation_id] = now
        return True

    def _cached_unified_response(self, page: int, page_size: int, filter_state: str, search: str) -> dict[str, Any]:
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

    def _unified_cache_file(self) -> Any:
        path = str(self.UNIFIED_CACHE_PATH or "").strip()
        if not path:
            return ""
        return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)

    def _persist_unified_cache_to_disk(self) -> None:
        if not self.PERSIST_UNIFIED_CACHE:
            return
        cache_file = self._unified_cache_file()
        if not cache_file:
            return
        try:
            cache_dir = os.path.dirname(cache_file)
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
            payload: dict[str, Any] = {
                "updated_at": utc_now().isoformat(),
                "chats": list(self._unified_chats_cache or []),
                "has_more": bool(self._unified_chats_cache_has_more),
                "total": int(self._unified_chats_cache_total or len(self._unified_chats_cache or [])),
                "next_cursor": self._unified_chats_cache_next_cursor,
                "page_size": self._unified_chats_cache_page_size,
                "counters": dict(self._index_counters_cache or self._empty_counters()),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not persist unified cache to disk: {e}")

    def _load_unified_cache_from_disk(self) -> None:
        if not self.PERSIST_UNIFIED_CACHE:
            return
        cache_file = self._unified_cache_file()
        if not cache_file or not os.path.exists(cache_file):
            return
        try:
            with open(cache_file, encoding="utf-8") as f:
                payload = json.load(f) or {}
            chats = payload.get("chats")
            if not isinstance(chats, list) or not chats:
                return

            updated_at_raw = payload.get("updated_at")
            if updated_at_raw:
                try:
                    updated_at = self._parse_timestamp(updated_at_raw)
                    age = (utc_now() - updated_at).total_seconds()
                    if age > max(60, int(self.UNIFIED_DISK_CACHE_MAX_AGE_SECONDS)):
                        return
                except Exception:
                    pass

            self._unified_chats_cache = chats
            self._unified_chats_cache_has_more = bool(payload.get("has_more"))
            self._unified_chats_cache_total = int(payload.get("total") or len(chats))
            self._unified_chats_cache_next_cursor = payload.get("next_cursor")
            self._unified_chats_cache_page_size = payload.get("page_size")
            counters = payload.get("counters")
            if isinstance(counters, dict):
                merged = self._empty_counters()
                merged.update({k: int(v) for k, v in counters.items() if k in merged})
                self._index_counters_cache = merged
            self._unified_chats_cache_time = utc_now()
            print(f"[live_chat:unified] loaded disk cache chats={len(chats)} file={cache_file}")
        except Exception as e:
            print(f"⚠️ Could not load unified cache from disk: {e}")

    def _stale_unified_fallback(
        self, page: int, page_size: int, filter_state: str, search: str
    ) -> dict[str, Any] | None:
        """Serve memory or disk cache when live index reads fail — never invent rows."""
        if self._unified_chats_cache:
            resp = self._cached_unified_response(page, page_size, filter_state, search)
            resp["source"] = "memory_cache"
            return resp
        self._load_unified_cache_from_disk()
        if self._unified_chats_cache:
            resp = self._cached_unified_response(page, page_size, filter_state, search)
            resp["source"] = "disk_cache"
            return resp
        return None

    def _empty_unified_response(
        self, page: int, page_size: int, filter_state: str, search: str, source: str
    ) -> dict[str, Any]:
        is_legitimate_empty = source in {"index_empty"}
        payload: dict[str, Any] = {
            "success": is_legitimate_empty,
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
        if not is_legitimate_empty:
            payload["error"] = "Could not load conversations."
        return payload

    async def _run_blocking_with_timeout(self, fn: Any, timeout_seconds: float) -> Any:
        timeout = max(0.1, float(timeout_seconds or 0))
        task = asyncio.create_task(asyncio.to_thread(fn))
        done, pending = await asyncio.wait({task}, timeout=timeout)
        if not done:
            for p in pending:
                p.cancel()
            raise TimeoutError()
        return task.result()

    async def _get_doc_with_timeout(self, doc_ref: Any, timeout_seconds: float | None = None) -> Any:
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
                raise TimeoutError() from e
            raise

    def _format_single_message(self, msg: dict[str, Any]) -> dict[str, Any]:
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
