from __future__ import annotations

import asyncio
import datetime
from typing import Any

import config
from services.live_chat_contracts import (
    utc_now,
)
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
)


class LiveChatDetailsMixin:
    """Conversation details, FAQ match context, message edits, metrics."""

    async def get_conversation_details(
        self,
        user_id: str,
        conversation_id: str,
        max_messages: int = 100,
        days: int = 0,
        before: str | None = None,
        day_window: int = 0,
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
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

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
                                "status": self._conversation_state_to_status(str(data.get("conversation_state") or "")),
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
            status = str(payload.get("status") or "active")

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

    async def get_faq_match_context(self, user_id: str, conversation_id: str, message_id: str) -> dict[str, Any]:
        """
        Get faq_match metadata and current FAQ entry for a message (for FAQ correction modal).
        Returns faq_match from message metadata and current_entry (question, answer) if faq_id exists.
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

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
                return {"success": False, "error": "Conversation not found"}

            doc_data = conv_doc.to_dict() or {}
            messages = doc_data.get("messages", [])
            message_id_str = str(message_id).strip()

            def _msg_id(m: dict[str, Any]) -> str:
                mid = m.get("message_id")
                if mid:
                    return str(mid).strip()
                meta = m.get("metadata") or {}
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
                    idx = (
                        (int(faq_id) - 1)
                        if isinstance(faq_id, int)
                        else (int(faq_id) - 1 if isinstance(faq_id, str) and faq_id.isdigit() else -1)
                    )
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
    ) -> dict[str, Any]:
        """
        Update a single message's text in a conversation (e.g. operator edit after dislike).
        Updates Firestore, invalidates cache, and broadcasts message_updated for real-time UI.
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

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
                return {"success": False, "error": "Conversation not found"}

            doc_data = conv_doc.to_dict() or {}
            messages = list(doc_data.get("messages", []))
            message_id_str = str(message_id).strip()
            if not message_id_str:
                return {"success": False, "error": "message_id is required"}

            def _msg_id(m: dict[str, Any]) -> str:
                mid = m.get("message_id")
                if mid:
                    return str(mid).strip()
                meta = m.get("metadata") or {}
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

            await asyncio.to_thread(
                conv_ref.update,
                {
                    "messages": messages,
                    "last_updated": utc_now(),
                },
            )
            self.invalidate_cache()

            updated_msg = messages[found_index]
            dash_msg = {
                "message_id": message_id_str,
                "content": new_text,
                "text": new_text,
                "timestamp": updated_msg.get("timestamp"),
                "is_user": updated_msg.get("role") == "user",
                "handled_by": (updated_msg.get("metadata") or {}).get("handled_by")
                or updated_msg.get("handled_by")
                or "bot",
                "role": updated_msg.get("role"),
            }

            try:
                from modules.live_chat_api import broadcast_sse_event

                asyncio.create_task(
                    broadcast_sse_event(
                        "message_updated",
                        {
                            "user_id": user_id,
                            "conversation_id": conversation_id,
                            "message_id": message_id_str,
                            "message": dash_msg,
                        },
                    )
                )
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
