from __future__ import annotations

# handlers/text_handlers_firestore.py
# Shared imports and utilities for all text handler modules
import asyncio
import datetime
import random
import re
from collections import deque
from typing import Any

import config
from handlers.training_handlers import exit_training_mode as original_exit_training_mode
from handlers.training_handlers import handle_training_input
from handlers.training_handlers import start_training_mode as original_start_training_mode
from services.api_integrations import check_customer_gender, create_customer, get_customer_by_phone, log_report_event
from services.chat_response_service import get_bot_chat_response
from services.gender_recognition_service import get_gender_from_gpt
from services.local_qa_service import local_qa_service
from services.qa_database_service import get_qa_response
from services.sentiment_escalation_service import sentiment_service
from services.user_persistence_service import user_persistence
from utils.utils import (
    count_tokens,
    detect_language,
    get_canonical_user_id_and_phone,
    get_conversation_context_for_gpt,
    get_conversation_history_from_firestore,
    get_conversation_last_ai_response_at,
    get_firestore_db,
    get_last_bot_message_for_gpt_context,
    get_last_bot_message_from_conversation,
    get_system_instruction,
    notify_human_on_whatsapp,
    save_conversation_message_to_firestore,
    save_for_training_conversation_log,
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
    "count_tokens",
    "save_for_training_conversation_log",
    "get_system_instruction",
    "save_conversation_message_to_firestore",
    "update_dashboard_metric_in_firestore",
    "set_human_takeover_status",
    "get_firestore_db",
    "get_conversation_history_from_firestore",
    "get_conversation_context_for_gpt",
    "get_conversation_last_ai_response_at",
    "get_last_bot_message_from_conversation",
    "get_last_bot_message_for_gpt_context",
    "get_canonical_user_id_and_phone",
    "get_gender_from_gpt",
    "get_bot_chat_response",
    "log_report_event",
    "check_customer_gender",
    "get_customer_by_phone",
    "create_customer",
    "sentiment_service",
    "get_qa_response",
    "local_qa_service",
    "user_persistence",
    "handle_training_input",
    "original_start_training_mode",
    "original_exit_training_mode",
    "_delayed_processing_tasks",
]
