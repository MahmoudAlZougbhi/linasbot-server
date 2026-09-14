from __future__ import annotations

# handlers/text_handlers_firestore.py
# Shared imports / re-exports for text handler modules (not Firestore-only).
# Kept under this filename for historical import paths — do not git-mv without a
# coordinated barrel update.
import asyncio
import datetime
import random
import re
from collections import deque
from typing import Any

import config
from services.gender_recognition_service import get_gender_from_gpt
from services.sentiment_escalation_service import sentiment_service
from services.team.user_persistence_service import user_persistence
from utils.utils import (
    detect_language,
    get_canonical_user_id_and_phone,
    get_conversation_history_from_firestore,
    get_conversation_last_ai_response_at,
    get_firestore_db,
    get_last_bot_message_from_conversation,
    notify_human_on_whatsapp,
    save_conversation_message_to_firestore,
    set_human_takeover_status,
    update_dashboard_metric_in_firestore,
)

# Shared dictionary to hold delayed processing tasks for each user
_delayed_processing_tasks: dict[str, Any] = {}

__all__ = [
    "asyncio",
    "datetime",
    "random",
    "deque",
    "re",
    "config",
    "detect_language",
    "notify_human_on_whatsapp",
    "save_conversation_message_to_firestore",
    "update_dashboard_metric_in_firestore",
    "set_human_takeover_status",
    "get_firestore_db",
    "get_conversation_history_from_firestore",
    "get_conversation_last_ai_response_at",
    "get_last_bot_message_from_conversation",
    "get_canonical_user_id_and_phone",
    "get_gender_from_gpt",
    "sentiment_service",
    "user_persistence",
    "_delayed_processing_tasks",
]
