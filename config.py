from __future__ import annotations

# config.py
import datetime
import os
from collections import defaultdict, deque
from typing import Any

from storage.persistent_storage import (
    ensure_dirs,
)

# --- API Keys and Tokens ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Customer Brain retrieval (Voyage). Do not reuse OPENAI_API_KEY for embeddings.
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
MESSAGE_BILLING_ENABLED = os.getenv("MESSAGE_BILLING_ENABLED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MESSAGE_BILLING_CUTOVER = os.getenv("MESSAGE_BILLING_CUTOVER", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FREE_PLAN_ENFORCEMENT_ENABLED = os.getenv("FREE_PLAN_ENFORCEMENT_ENABLED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LINAS_CUSTOMER_AI_LAB = os.getenv("LINAS_CUSTOMER_AI_LAB", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# WhatsApp Meta Cloud API
# These are fetched from your .env file
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")  # The access token for Meta Graph API
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")  # Your specific WhatsApp phone number ID
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")  # Your WhatsApp Business Account ID

EXTERNAL_API_BASE_URL = (os.getenv("EXTERNAL_API_BASE_URL") or "").strip()
EXTERNAL_API_TOKEN = os.getenv("EXTERNAL_API_TOKEN")

# --- Firebase Firestore Configuration (NEW) ---
# Path to your Firebase service account key JSON file.
# Prefer FIRESTORE_SERVICE_ACCOUNT_KEY_PATH / GOOGLE_APPLICATION_CREDENTIALS in
# production; the data/firebase_data.json default is for local/dev only (SEC-025).
FIRESTORE_SERVICE_ACCOUNT_KEY_PATH = (
    os.getenv("FIRESTORE_SERVICE_ACCOUNT_KEY_PATH")
    or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    or "data/firebase_data.json"
).strip() or "data/firebase_data.json"

# Firestore Collection Names (NEW)
FIRESTORE_CONVERSATIONS_COLLECTION = "conversations"  # Collection for storing chat logs
FIRESTORE_METRICS_COLLECTION = "dashboardMetrics"  # Collection for dashboard summary metrics

# Testing Mode Flag (NEW)
TESTING_MODE = False  # When True, Firebase saving is disabled for testing

# AI-primary orchestration mode:
# - True: AI decides conversation action/routing; backend executes.
# - False: Use code-first router short-circuit logic.
AI_PRIMARY_ORCHESTRATION = os.getenv("AI_PRIMARY_ORCHESTRATION", "true").strip().lower() == "true"
# After operator releases chat to bot: block auto re-escalation (handover_degree / error→handover) for this many minutes.
POST_TAKEOVER_ESCALATION_COOLDOWN_MINUTES = int(os.getenv("POST_TAKEOVER_ESCALATION_COOLDOWN_MINUTES", "45"))

# --- Local / development environment (same APIs as prod, safe messaging) ---
# Set APP_MODE=local or ENV=development to run locally with real APIs but controlled sending.
APP_MODE = os.getenv("APP_MODE", "").strip().lower()  # "local" = local env
ENV = os.getenv("ENV", "").strip().lower()  # "development" = local env
# When False: all outbound WhatsApp is dry-run (log + "would send", no real send).
ENABLE_SENDING = os.getenv("ENABLE_SENDING", "true").strip().lower() == "true"
# Comma-separated list of phone numbers allowed to receive real messages in local mode (sandbox/test).
# Only used when APP_MODE=local or ENV=development and ENABLE_SENDING=true.
_LOCAL_ALLOWED_RAW = os.getenv("LOCAL_ALLOWED_WHATSAPP_NUMBERS", "").strip()
LOCAL_ALLOWED_WHATSAPP_NUMBERS = {n.strip() for n in _LOCAL_ALLOWED_RAW.split(",") if n.strip()}


def is_local_env() -> bool:
    """True when running in local/development mode (same external APIs, safe messaging)."""
    return APP_MODE == "local" or ENV == "development"


def is_production_runtime() -> bool:
    """True when ENV/ENVIRONMENT/APP_ENV explicitly marks production (fail-closed helpers)."""
    for key in ("ENVIRONMENT", "ENV", "APP_ENV"):
        val = (os.getenv(key) or "").strip().lower()
        if val in {"prod", "production", "live"}:
            return True
    return False


# --- Bot Operational Settings ---
# WhatsApp Number for Human Notifications (e.g., your admin/staff number)
WHATSAPP_TO = os.getenv("WHATSAPP_TO")

# FFMPEG Path for voice message processing
FFMPEG_PATH = os.getenv("FFMPEG_PATH")

# --- User State Management (DefaultDicts for easy access) ---
user_context: defaultdict[str, deque[Any]] = defaultdict(deque)  # Stores conversation history for each user
user_gender: defaultdict[str, str] = defaultdict(str)  # Stores detected gender for each user
user_names: defaultdict[str, str] = defaultdict(str)  # Stores first name of each user
user_greeting_stage: defaultdict[str, int] = defaultdict(int)  # Tracks greeting stage for each user
gender_attempts: defaultdict[str, int] = defaultdict(int)  # Counts attempts to ask for gender
user_in_training_mode: defaultdict[str, bool] = defaultdict(bool)  # Flag if user is in training mode
user_photo_analysis_count: defaultdict[str, int] = defaultdict(int)  # Counts photo analysis per user
user_last_bot_response_time: defaultdict[str, datetime.datetime] = defaultdict(
    lambda: datetime.datetime.now()
)  # Last time bot responded to user
user_pending_messages: defaultdict[str, deque[Any]] = defaultdict(
    deque
)  # Queue for combining rapid messages from a user

# Dictionary to store user-specific data that replaces Telegram's context.user_data
# This will hold things like 'user_preferred_lang', 'initial_user_query_to_process', etc.
user_data_whatsapp: defaultdict[str, dict[str, Any]] = defaultdict(dict)

# --- Conversation State Schema (AI Smart Employee Architecture) ---
# Canonical fields for user_conversation_state (stored in user_data_whatsapp):
# - gender, awaiting_gender, awaiting_clarification, awaiting_name
# - original_question, clarification_target, selected_service, last_bot_question_type
# - human_handover_active (synced from config.user_in_human_takeover_mode)
DEFAULT_CONVERSATION_STATE = {
    "awaiting_gender": False,
    "awaiting_clarification": False,
    "awaiting_name": False,  # alias: awaiting_name_input
    "original_question": None,
    "clarification_target": None,
    "selected_service": None,
    "last_bot_question_type": None,
}


def ensure_conversation_state(user_data: dict) -> dict:
    """Ensure all conversation state fields exist in user_data. Returns user_data (mutated)."""
    for key, default in DEFAULT_CONVERSATION_STATE.items():
        if key not in user_data:
            user_data[key] = default
    # Sync awaiting_name from legacy awaiting_name_input
    if "awaiting_name_input" in user_data:
        user_data["awaiting_name"] = user_data.get("awaiting_name_input", False)
    return user_data


def get_conversation_state(user_id: str, user_data: dict) -> dict:
    """Build full conversation state for router (gender from config, rest from user_data)."""
    ensure_conversation_state(user_data)
    return {
        "gender": user_gender.get(user_id, "unknown"),
        "awaiting_gender": user_data.get("awaiting_gender", False),
        "awaiting_clarification": user_data.get("awaiting_clarification", False)
        or bool(user_data.get("pending_clarification_query")),
        "awaiting_name": user_data.get("awaiting_name", False) or user_data.get("awaiting_name_input", False),
        "original_question": user_data.get("original_question")
        or user_data.get("pending_clarification_query")
        or user_data.get("initial_user_query_to_process"),
        "clarification_target": user_data.get("clarification_target"),
        "selected_service": user_data.get("selected_service"),
        "last_bot_question_type": user_data.get("last_bot_question_type"),
        "human_handover_active": user_in_human_takeover_mode.get(user_id, False),
    }


# NEW: AI Takeover State for each user
user_in_human_takeover_mode: defaultdict[str, bool] = defaultdict(
    bool
)  # Flag if a specific user's chat is taken over by human
# Rate limit for "waiting" auto-reply when user keeps messaging while in waiting queue (seconds)
user_last_waiting_reply_sent: defaultdict[str, datetime.datetime] = defaultdict(lambda: datetime.datetime.min)
WAITING_REPLY_COOLDOWN_SECONDS = 60

# HA conversation session still snapshots this blob; live Brain does not collect booking FSM.
user_booking_state: defaultdict[str, dict[str, Any]] = defaultdict(dict)


# --- Constants and Limits ---
MAX_PHOTO_ANALYSIS_PER_USER = 10  # Maximum number of photos a user can request analysis for
ENFORCE_TOTAL_PHOTO_ANALYSIS_LIMIT = False  # If False, do not enforce conversation-wide photo limit
MAX_IMAGES_PER_SINGLE_MESSAGE = 10  # Hard limit per single inbound message
MAX_TEXT_LINES_PER_SINGLE_MESSAGE = 30  # Hard limit per single inbound text message
MAX_CONTEXT_MESSAGES = 20  # Max number of messages to keep in conversation context
# Context window for AI memory:
# - Include only messages from the last N hours in GPT context.
# - If MAX_CONTEXT_MESSAGES_IN_WINDOW = 0, do not apply a hard count cap after time filtering.
CONTEXT_WINDOW_HOURS = int(os.getenv("CONTEXT_WINDOW_HOURS", "12"))
MAX_CONTEXT_MESSAGES_IN_WINDOW = int(os.getenv("MAX_CONTEXT_MESSAGES_IN_WINDOW", "0"))
MAX_RELEVANT_CUSTOM_QA = 3  # Max relevant custom Q&A entries to fetch
MAX_GENDER_ASK_ATTEMPTS = 3  # Max times bot will ask for gender before suggesting human handover

# Delay for combining rapid messages from a user (e.g., multiple short texts sent quickly)
# Requirement: wait 3 seconds after the LAST message before responding.
MESSAGE_COMBINING_DELAY = 3.0  # seconds


# --- Bot Welcome Messages (Language-specific) ---
# Generic WhatsApp boot copy. Published CM welcome / ai_basics override this.
# Override per language via WELCOME_MESSAGE_<LANG>.
def _welcome_message(lang: str, default: str) -> str:
    return (os.getenv(f"WELCOME_MESSAGE_{lang.upper()}") or "").strip() or default


WELCOME_MESSAGES = {
    "ar": _welcome_message("ar", "مرحباً! كيف يمكنني مساعدتك؟"),
    "en": _welcome_message("en", "Hello! How can I help you today?"),
    "fr": _welcome_message("fr", "Bonjour ! Comment puis-je vous aider ?"),
    "franco": _welcome_message("franco", "مرحباً! كيف يمكنني مساعدتك؟"),
}

# --- Bot Knowledge Base (Loaded from files) ---
PRICE_LIST = ""
BOT_STYLE_GUIDE = ""
CORE_KNOWLEDGE_BASE = ""
SYSTEM_PROMPT_TEMPLATE = ""


def load_bot_assets() -> None:
    """SaaS is published-CM only — clinic file corpus is never injected."""
    global PRICE_LIST, BOT_STYLE_GUIDE, CORE_KNOWLEDGE_BASE, SYSTEM_PROMPT_TEMPLATE

    ensure_dirs()
    PRICE_LIST = ""
    BOT_STYLE_GUIDE = ""
    CORE_KNOWLEDGE_BASE = ""
    SYSTEM_PROMPT_TEMPLATE = ""


# --- Initialize Bot Assets on startup ---
load_bot_assets()
