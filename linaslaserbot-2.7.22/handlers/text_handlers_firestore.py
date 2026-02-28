# handlers/text_handlers_firestore.py
# Shared imports and utilities for all text handler modules

import asyncio
import datetime
import random
from collections import deque
import re

import config
from utils.utils import (
    detect_language,
    notify_human_on_whatsapp,
    count_tokens,
    save_for_training_conversation_log,
    get_system_instruction,
    save_conversation_message_to_firestore,
    update_dashboard_metric_in_firestore,
    set_human_takeover_status,
    get_firestore_db,
    get_conversation_history_from_firestore
)
from services.gender_recognition_service import get_gender_from_gpt
from services.chat_response_service import get_bot_chat_response
from services.api_integrations import log_report_event, check_customer_gender, get_customer_by_phone, create_customer
from services.sentiment_escalation_service import sentiment_service
from services.qa_database_service import get_qa_response
from services.local_qa_service import local_qa_service
from services.user_persistence_service import user_persistence
from handlers.training_handlers import handle_training_input, start_training_mode as original_start_training_mode, exit_training_mode as original_exit_training_mode

# Shared dictionary to hold delayed processing tasks for each user
_delayed_processing_tasks = {}

# Locks for message merge: concurrency-safe per user when webhook receives rapid messages
_message_merge_locks = {}
_message_merge_dict_lock = asyncio.Lock()


async def get_message_merge_lock(user_id: str) -> asyncio.Lock:
    """Get or create asyncio.Lock for user_id. Concurrency-safe."""
    async with _message_merge_dict_lock:
        if user_id not in _message_merge_locks:
            _message_merge_locks[user_id] = asyncio.Lock()
        return _message_merge_locks[user_id]


__all__ = [
    'asyncio', 'datetime', 'random', 'deque', 're', 'config',
    'detect_language', 'notify_human_on_whatsapp', 'count_tokens',
    'save_for_training_conversation_log', 'get_system_instruction',
    'save_conversation_message_to_firestore', 'update_dashboard_metric_in_firestore',
    'set_human_takeover_status', 'get_firestore_db', 'get_conversation_history_from_firestore',
    'get_gender_from_gpt', 'get_bot_chat_response', 'log_report_event',
    'check_customer_gender', 'get_customer_by_phone', 'create_customer',
    'sentiment_service', 'get_qa_response', 'local_qa_service', 'user_persistence',
    'handle_training_input', 'original_start_training_mode', 'original_exit_training_mode',
    '_delayed_processing_tasks',
    'get_message_merge_lock',
]
