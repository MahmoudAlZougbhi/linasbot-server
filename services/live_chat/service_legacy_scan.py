"""Legacy Live Chat conversation scan — not used on request paths."""

from __future__ import annotations

from typing import Any

import config
from services.live_chat.contracts import (
    normalize_conversation_document,
    utc_now,
)
from services.live_chat.service_common import _live_chat_display_name


class LiveChatLegacyScanMixin:
    """Kept only so rebuild/debug tooling can call a full conversation scan."""

    STATE_ASSIGNED: Any
    STATE_BOT_ACTIVE: Any
    STATE_WAITING_OPERATOR: Any
    _filter_conversations: Any
    _get_users_collection: Any
    _is_live_window: Any
    _normalize_conversation_state: Any
    _parse_timestamp: Any
    _resolve_user_phone: Any
    _stream_conversations_for_users: Any
    _stream_user_docs: Any
    _visible_chat_messages: Any

    async def _legacy_active_scan_for_fallback(
        self, search: str | None = None, user_limit: int | None = None
    ) -> list[dict[str, Any]]:
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
