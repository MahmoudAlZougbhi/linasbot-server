"""
Live Chat Service - Canonical conversation_state
- 6-hour time filter for active conversations
- Canonical conversation_state drives UI and persistence
- Firestore is source of truth; caches only accelerate reads
- Auto-reopen on new message
"""

from __future__ import annotations

import datetime
import os
from collections import defaultdict
from typing import Any

from services.live_chat_service_common import _env_bool, _env_float, _env_int
from services.live_chat_service_details import LiveChatDetailsMixin
from services.live_chat_service_history import LiveChatHistoryMixin
from services.live_chat_service_history_api import LiveChatHistoryApiMixin
from services.live_chat_service_index import LiveChatIndexMixin
from services.live_chat_service_lifecycle import LiveChatLifecycleMixin
from services.live_chat_service_operator import LiveChatOperatorMixin
from services.live_chat_service_phone import LiveChatPhoneMixin
from services.live_chat_service_rebuild import LiveChatRebuildMixin
from services.live_chat_service_templates import LiveChatTemplatesMixin
from services.live_chat_service_unified import LiveChatUnifiedMixin


class LiveChatService(
    LiveChatIndexMixin,
    LiveChatRebuildMixin,
    LiveChatHistoryMixin,
    LiveChatUnifiedMixin,
    LiveChatTemplatesMixin,
    LiveChatHistoryApiMixin,
    LiveChatLifecycleMixin,
    LiveChatOperatorMixin,
    LiveChatDetailsMixin,
    LiveChatPhoneMixin,
):
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
    FIRESTORE_QUERY_TIMEOUT_SECONDS = _env_float("LIVECHAT_QUERY_TIMEOUT_SECONDS", 12)
    RECENT_MESSAGES_IN_INDEX = 30
    INDEX_READ_TIMEOUT_SECONDS = _env_float("LIVECHAT_INDEX_READ_TIMEOUT_SECONDS", 3)
    INDEX_WRITE_TIMEOUT_SECONDS = _env_float("LIVECHAT_INDEX_WRITE_TIMEOUT_SECONDS", 4)
    INDEX_REFRESH_TIMEOUT_SECONDS = _env_float("LIVECHAT_INDEX_REFRESH_TIMEOUT_SECONDS", 4)
    INDEX_WRITE_COOLDOWN_SECONDS = _env_int("LIVECHAT_INDEX_WRITE_COOLDOWN_SECONDS", 180)
    # Short default so badge counts track tab filters soon after release/takeover (was 180s → visible flicker).
    INDEX_COUNTERS_CACHE_TTL = _env_int("LIVECHAT_INDEX_COUNTERS_CACHE_TTL_SECONDS", 25)
    INDEX_COUNTER_SCAN_LIMIT = _env_int("LIVECHAT_INDEX_COUNTER_SCAN_LIMIT", 250)
    INDEX_REFRESH_MIN_INTERVAL_SECONDS = _env_int("LIVECHAT_INDEX_REFRESH_MIN_INTERVAL_SECONDS", 120)
    SEARCH_WIDEN_MAX_DOCS = _env_int("LIVECHAT_SEARCH_WIDEN_MAX_DOCS", 1000)
    ENABLE_INDEX_BACKFILL_ON_READ = _env_bool("LIVECHAT_ENABLE_INDEX_BACKFILL_ON_READ", False)
    ENABLE_WAITING_QUEUE_FALLBACK_SCAN = _env_bool("LIVECHAT_ENABLE_WAITING_QUEUE_FALLBACK_SCAN", True)
    FALLBACK_USERS_STREAM_LIMIT = 80
    FALLBACK_SEARCH_USERS_LIMIT = 150
    FALLBACK_UNIFIED_TIMEOUT_SECONDS = _env_int("LIVECHAT_FALLBACK_UNIFIED_TIMEOUT_SECONDS", 20)
    WAITING_SOURCE_USERS_LIMIT = _env_int("LIVECHAT_WAITING_SOURCE_USERS_LIMIT", 1200)
    PERSIST_UNIFIED_CACHE = _env_bool("LIVECHAT_PERSIST_UNIFIED_CACHE", True)
    UNIFIED_DISK_CACHE_MAX_AGE_SECONDS = _env_int("LIVECHAT_UNIFIED_DISK_CACHE_MAX_AGE_SECONDS", 86400)
    UNIFIED_CACHE_PATH = os.getenv("LIVECHAT_UNIFIED_CACHE_PATH", "data/live_chat_unified_cache.json")

    # Canonical conversation states
    STATE_BOT_ACTIVE = "bot_active"
    STATE_WAITING_OPERATOR = "waiting_for_operator"
    STATE_ASSIGNED = "assigned_to_operator"
    STATE_RESOLVED = "resolved"
    STATE_ARCHIVED = "archived"

    INDEX_COLLECTION = "live_chat_index"

    def __init__(self) -> None:
        self.operator_status: defaultdict[str, str] = defaultdict(lambda: "available")
        self.operator_sessions: dict[str, Any] = {}
        # Cache for active conversations
        self._conversations_cache: list[dict[str, Any]] | None = None
        self._conversations_cache_time: datetime.datetime | None = None
        # Cache for waiting queue
        self._queue_cache: list[dict[str, Any]] | None = None
        self._queue_cache_time: datetime.datetime | None = None
        # Cache for static phone<->room mapping file
        self._phone_to_room_cache: dict[str, str] = {}
        self._room_to_phone_cache: dict[str, str] = {}
        self._phone_mapping_cache_time: datetime.datetime | None = None
        # Cache for unified chats (WhatsApp-style list)
        self._unified_chats_cache: list[dict[str, Any]] = []
        self._unified_chats_cache_time: datetime.datetime | None = None
        self._unified_chats_cache_has_more = False
        self._unified_chats_cache_total = 0
        self._unified_chats_cache_next_cursor: str | None = None
        self._unified_chats_cache_page_size: int | None = None
        self._index_counters_cache = self._empty_counters()
        self._index_counters_cache_time: datetime.datetime | None = None
        self._index_write_paused_until: datetime.datetime | None = None
        # Prevent duplicate index writes for identical payloads.
        self._index_signature_cache: dict[str, Any] = {}
        # Throttle read-path index refreshes for the same conversation.
        self._read_path_refresh_tracker: dict[str, datetime.datetime] = {}
        self._load_unified_cache_from_disk()


# Global instance
live_chat_service = LiveChatService()
