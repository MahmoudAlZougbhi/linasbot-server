from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore

import config
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


class LiveChatRebuildMixin:
    """Index rebuild, upsert, and refresh helpers."""

    async def _sync_index_from_source(
        self, user_id: str, conversation_id: str, *, allow_state_backfill: bool = False
    ) -> dict[str, Any]:
        """Read canonical conversation from Firestore, normalize, and upsert index entry."""
        db = get_firestore_db()
        if not db:
            return {"written": False, "reason": "firestore_missing"}

        conv_ref, conv_snap, resolved_user_id = await self._resolve_conversation_doc_ref(
            db,
            user_id,
            conversation_id,
        )
        if not conv_snap.exists:
            return {"written": False, "reason": "missing"}

        raw_payload = conv_snap.to_dict() or {}
        conv_data = self._canonical_conversation(conversation_id, resolved_user_id, raw_payload)
        entry = self._build_index_entry(resolved_user_id, conv_data, conv_data.get("visible_messages", []))

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
            "resolved_user_id": resolved_user_id,
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
        max_users: int | None = None,
        max_conversations_per_user: int | None = None,
        set_conversation_state: bool = True,
        return_details: bool = False,
    ) -> int | dict[str, int]:
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

        async def _bounded(user_id: str) -> Any:
            async with semaphore:
                try:
                    conversations_collection = users_collection.document(user_id).collection(
                        config.FIRESTORE_CONVERSATIONS_COLLECTION
                    )
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
        user_name = _live_chat_display_name(
            customer_info.get("name"),
            config.user_names.get(str(user_id or "")),
        )
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
        is_live = state in {
            self.STATE_BOT_ACTIVE,
            self.STATE_WAITING_OPERATOR,
            self.STATE_ASSIGNED,
        } and self._is_live_window(last_ts)

        recent_messages = []
        if messages:
            tail = (
                messages[-self.RECENT_MESSAGES_IN_INDEX :]
                if len(messages) > self.RECENT_MESSAGES_IN_INDEX
                else messages
            )
            for m in tail:
                try:
                    recent_messages.append(self._format_single_message(m))
                except Exception:
                    pass

        crm_exists = customer_info.get("crm_customer_exists")
        is_new_customer = crm_exists is False
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
            "human_takeover_active": bool(conv_data.get("human_takeover_active")),
            "post_release_escalation_suppressed_until": conv_data.get("post_release_escalation_suppressed_until"),
            "operator_id": conv_data.get("operator_id"),
            "unread_count": unread_count,
            "sentiment": sentiment,
            "is_live": is_live,
            "language": language,
            "customer_info": customer_info,
            "is_new_customer": is_new_customer,
        }
        if recent_messages:
            out["recent_messages"] = recent_messages
        return out

    async def _upsert_index_entry(self, entry: dict) -> None:
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
                str(payload.get("human_takeover_active")),
                str(payload.get("post_release_escalation_suppressed_until")),
            )
            if self._index_signature_cache.get(conv_id) == signature:
                print(f"[live_chat:index] skip unchanged write conv={conv_id}")
                return

            idx = self._index_collection(db).document(conv_id)
            await asyncio.to_thread(lambda: idx.set(payload, timeout=self.INDEX_WRITE_TIMEOUT_SECONDS))
            self._index_signature_cache[conv_id] = signature
        except Exception as e:
            print(f"⚠️ Failed upserting index entry for {entry.get('conversation_id')}: {e}")
            lowered = str(e).lower()
            if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
                self._pause_index_writes("index write timeout")
            if "429" in lowered or "quota" in lowered or "resource exhausted" in lowered:
                self._pause_index_writes(str(e))

    async def _refresh_index_for_conversation(self, user_id: str, conv_id: str) -> None:
        try:
            if self._is_index_write_paused():
                return
            result = await asyncio.wait_for(
                self._sync_index_from_source(user_id, conv_id, allow_state_backfill=False),
                timeout=self.INDEX_REFRESH_TIMEOUT_SECONDS,
            )
            if not result.get("written"):
                print(f"⚠️ [index-refresh] skipped user={user_id} conv={conv_id} reason={result.get('reason')}")
                return
            print(
                f"🔄 [index-refresh] rebuilt index user={result.get('resolved_user_id', user_id)} conv={conv_id} state={result.get('conversation_state')}"
            )
        except TimeoutError:
            print(f"⚠️ [index-refresh] timeout user={user_id} conv={conv_id}")
        except Exception as e:
            print(f"⚠️ Failed to refresh index for {conv_id}: {e}")

    def invalidate_cache(self) -> None:
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
