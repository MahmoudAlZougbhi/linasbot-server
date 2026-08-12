from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any

import config
from services.live_chat_contracts import (
    parse_timestamp_utc,
    utc_now,
)
from utils.phone_utils import is_phone_like_user_id, normalize_phone


class LiveChatPhoneMixin:
    """Phone/room mapping and conversation search helpers."""

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

    def _filter_conversations(self, conversations: list[dict[str, Any]], search_term: str) -> list[dict[str, Any]]:
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

    def _choose_preferred_phone(self, current_phone: str | None, candidate_phone: str) -> str:
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

    def _load_phone_room_mapping(self) -> dict[str, str]:
        """Load `data/phone_to_room_mapping.json` with short TTL cache."""
        now = utc_now()
        if (
            self._phone_mapping_cache_time is not None
            and (now - self._phone_mapping_cache_time).total_seconds() < self.PHONE_MAPPING_CACHE_TTL
        ):
            return self._room_to_phone_cache

        phone_to_room = {}
        room_to_phone: dict[str, Any] = {}

        mapping_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "phone_to_room_mapping.json",
        )

        try:
            with open(mapping_path, encoding="utf-8") as mapping_file:
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
                    room_to_phone[room_id] = self._choose_preferred_phone(room_to_phone.get(room_id), phone_value)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"⚠️ Failed to load phone_to_room_mapping.json: {e}")

        self._phone_to_room_cache = phone_to_room
        self._room_to_phone_cache = room_to_phone
        self._phone_mapping_cache_time = now
        return self._room_to_phone_cache

    def _get_mapped_phone_for_room(self, user_id: str) -> str | None:
        """Return mapped phone for a room_id/user_id when available."""
        room_to_phone = self._load_phone_room_mapping()
        return room_to_phone.get(str(user_id))

    def _resolve_user_phone(self, user_id: str, customer_info: dict[str, Any] | None) -> tuple[str, str]:
        """
        Resolve best phone for dashboard/search:
        1) customer_info
        2) runtime memory (config.user_data_whatsapp)
        3) static phone_to_room_mapping.json
        """
        customer_info = customer_info or {}
        # Try both user_id formats (9613000000 vs +9613000000) for memory lookup
        user_data = config.user_data_whatsapp.get(user_id, {})
        if not user_data and user_id:
            alt_key = f"+{user_id}" if not str(user_id).startswith("+") else str(user_id).lstrip("+")
            user_data = config.user_data_whatsapp.get(alt_key, {})

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
        # Fallback: user_id may be the phone (e.g. 9613000000 from Firestore doc ID)
        if (not phone_full or phone_full == "Unknown") and is_phone_like_user_id(user_id):
            e164 = normalize_phone(user_id)
            if e164:
                phone_full = e164
                if not clean_digits:
                    clean_digits = self._normalize_phone_digits(user_id)
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

    def _parse_timestamp(self, timestamp: Any) -> datetime.datetime:
        """Parse various timestamp formats - always returns UTC-aware datetime"""
        return parse_timestamp_utc(timestamp)

    async def get_active_conversations(self, search: str = "") -> list[dict[str, Any]]:
        """Backward-compatible wrapper: return master inbox page 1 (no 6h filter)."""
        try:
            unified = await self.get_unified_chats(search=search, page=1, page_size=200)
            return [
                {
                    "conversation_id": c.get("conversation_id"),
                    "user_id": c.get("user_id"),
                    "user_name": c.get("user_name"),
                    "user_phone": c.get("phone_number"),
                    "phone_clean": c.get("phone_clean"),
                    "last_message": c.get("last_message_text"),
                    "last_activity": c.get("last_message_at"),
                    "status": c.get("conversation_state"),
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

    async def get_metrics(self) -> dict[str, Any]:
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
                    "active_operators": len(
                        [op for op, status in self.operator_status.items() if status == "available"]
                    ),
                    "time_window_hours": 6,
                },
                "timestamp": utc_now().isoformat(),
            }

        except Exception as e:
            print(f"❌ Error getting metrics: {e}")
            return {"success": False, "error": str(e)}
