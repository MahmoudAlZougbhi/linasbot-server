from __future__ import annotations

import asyncio
import datetime
from typing import Any

import config
from services.live_chat.contracts import (
    utc_now,
)
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
)


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
    invalidate_cache: Any
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
            from services.live_chat.tenant import normalize_live_chat_tenant_id, row_belongs_to_tenant

            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            workspace = normalize_live_chat_tenant_id(tenant_id)
            if workspace:
                visible = await self.thread_visible_to_tenant(
                    user_id=user_id, conversation_id=conversation_id, tenant_id=workspace
                )
                if not visible:
                    return {"success": False, "error": "Conversation not found"}

            app_id = "linas-ai-bot-backend"
            index_coll = self._index_collection(db)

            # Fast path: initial open (no days/before filter) — serve from index in <3s so UI opens in <5s
            if days <= 0 and not before:
                try:
                    index_ref = index_coll.document(conversation_id)
                    index_doc = await self._get_doc_with_timeout(
                        index_ref, timeout_seconds=self.INDEX_READ_TIMEOUT_SECONDS
                    )
                    if index_doc.exists:
                        data = index_doc.to_dict() or {}
                        data.setdefault("conversation_id", conversation_id)
                        data.setdefault("user_id", user_id)
                        if workspace and not row_belongs_to_tenant(data, workspace):
                            return {"success": False, "error": "Conversation not found"}
                        recent = data.get("recent_messages")
                        if isinstance(recent, list) and len(recent) > 0:
                            formatted_recent = [
                                self._format_single_message(msg) for msg in recent if isinstance(msg, dict)
                            ]
                            msg_count = int(data.get("message_count") or 0)
                            print(
                                f"[live_chat:conversation] source=index_recent conv={conversation_id} returned={len(formatted_recent)} total={msg_count}"
                            )
                            return {
                                "success": True,
                                "conversation_id": conversation_id,
                                "messages": formatted_recent,
                                "total_messages": msg_count,
                                "returned_messages": len(formatted_recent),
                                "has_more": msg_count > len(formatted_recent),
                                "sentiment": str(data.get("sentiment") or "neutral"),
                                "status": self._conversation_state_to_status(self._normalize_conversation_state(data)),
                            }
                except TimeoutError:
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
                except TimeoutError:
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
            status = self._conversation_state_to_status(self._normalize_conversation_state(payload))

            # Fast path for initial open (days=0, before not set):
            # avoid scanning/normalizing the full conversation history on every open.
            if days <= 0 and not before:
                tail_window = max(max_messages * 4, 100)
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
                    if days > 0 and cutoff is not None and (ts is None or ts < cutoff):
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
            has_more = messages_before_slice > max_messages if before else total_messages > max_messages

            out = {
                "success": True,
                "conversation_id": conversation_id,
                "messages": formatted_messages,
                "total_messages": total_messages,
                "returned_messages": len(formatted_messages),
                "has_more": has_more,
                "sentiment": sentiment,
                "status": status,
            }
            print(
                f"[live_chat:conversation] source=full_document conv={conversation_id} total_raw={total_messages} returned={len(formatted_messages)}"
            )
            #  read-path backfill (disabled by default to avoid write amplification)
            if (
                days <= 0
                and not before
                and self.ENABLE_INDEX_BACKFILL_ON_READ
                and self._should_schedule_read_path_refresh(conversation_id)
            ):
                asyncio.create_task(self._refresh_index_for_conversation(effective_user_id, conversation_id))
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
                    f.write(
                        json.dumps(
                            {
                                "sessionId": "420609",
                                "location": "live_chat_service:get_conversation_details",
                                "message": "service return",
                                "data": {
                                    "msg_count": len(formatted_messages),
                                    "first_ts": first_ts,
                                    "last_ts": last_ts,
                                },
                                "timestamp": int(__import__("time").time() * 1000),
                                "hypothesisId": "H1,H9",
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # #endregion
            return out

        except Exception as e:
            print(f"❌ Error getting conversation details: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}
