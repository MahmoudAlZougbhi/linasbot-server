# config.py
import os
from storage.persistent_storage import (
    KNOWLEDGE_BASE_FILE,
    PRICE_LIST_FILE,
    SYSTEM_PROMPT_TEMPLATE_FILE,
    STYLE_GUIDE_FILE,
    ensure_dirs,
)
from collections import defaultdict, deque
import json
import datetime

# --- API Keys and Tokens ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# WhatsApp Meta Cloud API
# These are fetched from your .env file
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN") # The access token for Meta Graph API
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID") # Your specific WhatsApp phone number ID
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") # Your WhatsApp Business Account ID

# Internal API for Lina’s Laser Clinic
LINASLASER_API_BASE_URL = os.getenv("LINASLASER_API_BASE_URL")
LINASLASER_API_TOKEN = os.getenv("LINASLASER_API_TOKEN")

# --- Firebase Firestore Configuration (NEW) ---
# Path to your Firebase service account key JSON file.
# This file is downloaded from Firebase Console -> Project settings -> Service accounts.
# Make sure to place it in the 'data' directory.
FIRESTORE_SERVICE_ACCOUNT_KEY_PATH = "data/firebase_data.json" # تم تحديث هذا المسار بناءً على اسم ملفك الجديد

# Firestore Collection Names (NEW)
FIRESTORE_CONVERSATIONS_COLLECTION = "conversations" # Collection for storing chat logs
FIRESTORE_METRICS_COLLECTION = "dashboardMetrics"   # Collection for dashboard summary metrics

# Testing Mode Flag (NEW)
TESTING_MODE = False  # When True, Firebase saving is disabled for testing

# AI-primary orchestration mode:
# - True: AI decides conversation action/routing; backend executes.
# - False: Use code-first router short-circuit logic.
AI_PRIMARY_ORCHESTRATION = os.getenv("AI_PRIMARY_ORCHESTRATION", "true").strip().lower() == "true"

# --- Local / development environment (same APIs as prod, safe messaging) ---
# Set APP_MODE=local or ENV=development to run locally with real APIs but controlled sending.
APP_MODE = os.getenv("APP_MODE", "").strip().lower()  # "local" = local env
ENV = os.getenv("ENV", "").strip().lower()            # "development" = local env
# When False: all outbound WhatsApp is dry-run (log + "would send", no real send).
ENABLE_SENDING = os.getenv("ENABLE_SENDING", "true").strip().lower() == "true"
# Comma-separated list of phone numbers allowed to receive real messages in local mode (sandbox/test).
# Only used when APP_MODE=local or ENV=development and ENABLE_SENDING=true.
_LOCAL_ALLOWED_RAW = os.getenv("LOCAL_ALLOWED_WHATSAPP_NUMBERS", "").strip()
LOCAL_ALLOWED_WHATSAPP_NUMBERS = {n.strip() for n in _LOCAL_ALLOWED_RAW.split(",") if n.strip()}

def is_local_env():
    """True when running in local/development mode (same external APIs, safe messaging)."""
    return APP_MODE == "local" or ENV == "development"

# --- Bot Operational Settings ---
# WhatsApp Number for Human Notifications (e.g., your admin/staff number)
WHATSAPP_TO = os.getenv("WHATSAPP_TO")
# Trainer's WhatsApp Number (for training mode access and daily reports)
TRAINER_WHATSAPP_NUMBER = os.getenv("TRAINER_WHATSAPP_NUMBER")

# FFMPEG Path for voice message processing
FFMPEG_PATH = os.getenv("FFMPEG_PATH")

# --- User State Management (DefaultDicts for easy access) ---
user_context = defaultdict(deque) # Stores conversation history for each user
user_gender = defaultdict(str) # Stores detected gender for each user
user_names = defaultdict(str) # Stores first name of each user
user_greeting_stage = defaultdict(int) # Tracks greeting stage for each user
gender_attempts = defaultdict(int) # Counts attempts to ask for gender
user_in_training_mode = defaultdict(bool) # Flag if user is in training mode
user_photo_analysis_count = defaultdict(int) # Counts photo analysis per user
user_last_bot_response_time = defaultdict(lambda: datetime.datetime.now()) # Last time bot responded to user
user_pending_messages = defaultdict(deque) # Queue for combining rapid messages from a user

# Dictionary to store user-specific data that replaces Telegram's context.user_data
# This will hold things like 'user_preferred_lang', 'initial_user_query_to_process', etc.
user_data_whatsapp = defaultdict(dict)

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
        "awaiting_clarification": user_data.get("awaiting_clarification", False) or bool(user_data.get("pending_clarification_query")),
        "awaiting_name": user_data.get("awaiting_name", False) or user_data.get("awaiting_name_input", False),
        "original_question": user_data.get("original_question") or user_data.get("pending_clarification_query") or user_data.get("initial_user_query_to_process"),
        "clarification_target": user_data.get("clarification_target"),
        "selected_service": user_data.get("selected_service"),
        "last_bot_question_type": user_data.get("last_bot_question_type"),
        "human_handover_active": user_in_human_takeover_mode.get(user_id, False),
    }

# NEW: AI Takeover State for each user
user_in_human_takeover_mode = defaultdict(bool) # Flag if a specific user's chat is taken over by human
# Rate limit for "waiting" auto-reply when user keeps messaging while in waiting queue (seconds)
user_last_waiting_reply_sent = defaultdict(lambda: datetime.datetime.min)
WAITING_REPLY_COOLDOWN_SECONDS = 60

# NEW: Booking State Tracking - persists booking progress across messages
# Tracks: service, body_area, machine, branch, date, etc.
user_booking_state = defaultdict(dict)

# For training handlers:
training_stage = defaultdict(int)
last_generated_qa_for_save = defaultdict(list)


# --- Constants and Limits ---
MAX_PHOTO_ANALYSIS_PER_USER = 10 # Maximum number of photos a user can request analysis for
MAX_CONTEXT_MESSAGES = 20 # Max number of messages to keep in conversation context (increased from 15 for better booking flow)
MAX_CONTEXT_MESSAGES_TRAINING = 10 # Max messages for training conversation context
MAX_RELEVANT_CUSTOM_QA = 3 # Max relevant custom Q&A entries to fetch
MAX_GENDER_ASK_ATTEMPTS = 3 # Max times bot will ask for gender before suggesting human handover

# Default IDs for booking (if not explicitly provided by user in conversation)
DEFAULT_BRANCH_ID = 1
DEFAULT_SERVICE_ID = 1
DEFAULT_MACHINE_ID = 1

# Delay for combining rapid messages from a user (e.g., multiple short texts sent quickly)
# Requirement: wait 3 seconds after the LAST message before responding.
MESSAGE_COMBINING_DELAY = 3.0 # seconds

# --- Bot Welcome Messages (Language-specific) ---
WELCOME_MESSAGES = {
    "ar": "مرحباً! 😊\nمعك مروى – المساعد الذكي بالذكاء الاصطناعي من مركز لينا ليزر.\nكيفك؟ كيف فيني ساعدك اليوم؟ 🧠✨\n\nفيك تحكيلي بأي طريقة بتحبها – حتى لو بالصوت! 🎤\nأنا هون مشان أساعدك بأي شي بدك ياه، بكل سهولة وسرعة.\nجاهز؟ يلا نحكي! 🤖💬\n\nوبالمناسبة، كرمال نقدر نساعدك ونقدم لك أفضل خدمة، ممكن تخبرنا لو سمحت إذا أنتَ شاباً أم صبية؟ 👦👧",
    "en": "Hello! 😊\nThis is Marwa AI Assistant – your smart AI assistant from Lina's Laser Center.\nHow are you? How can I help you today? 🧠✨\n\nYou can talk to me in any way you prefer – even with your voice! 🎤\nI'm here to help you with anything you need, easily and quickly.\nReady? Let's chat! 🤖💬\n\nBy the way, to help and serve you better, could you please tell us if you are male or female? 👦👧",
    "fr": "Bonjour ! 😊\nC'est Marwa AI Assistant – votre assistant intelligent de Lina's Laser Center.\nComment allez-vous ? Comment puis-je vous aider aujourd'hui ? 🧠✨\n\nYou can talk to me in any way you prefer – even by voice! 🎤\nI'm here to help you with anything you need, easily and quickly.\nReady? Let's chat! 🤖💬\n\nAu fait, afin de mieux vous aider et de vous offrir le meilleur service, pourriez-vous nous dire si vous êtes un homme ou une femme ? 👦👧",
    "franco": "مرحباً! 😊\nمعك مروى – المساعد الذكي بالذكاء الاصطناعي من مركز لينا ليزر.\nكيفك؟ كيف فيني ساعدك اليوم؟ 🧠✨\n\nفيك تحكيلي بأي طريقة بتحبها – حتى لو بالصوت! 🎤\nأنا هون مشان أساعدك بأي شي بدك ياه، بكل سهولة وسرعة.\nجاهز؟ يلا نحكي! 🤖💬\n\nوبالمناسبة، كرمال نقدر نساعدك ونقدم لك أفضل خدمة، ممكن تخبرنا لو سمحت إذا أنتَ شاباً أم صبية؟ 👦👧"
}

# --- Gender Question Variations ---
GENDER_QUESTIONS = {
    "ar": [
        "كرمال نقدر نساعدك ونفيدك بأفضل شكل، ممكن تخبرنا لو سمحت إذا أنتَ شب أو أنتِ صبية؟ 👦👧",
        "لنضمن لك تجربة مريحة ومميزة، فينا نعرف لو حضرتك شب أو صبية؟ 🙏😊",
        "لتقديم مساعدة أكثر دقة وودية، يا ريت تحدد لنا جنسك (شب/صبية)؟ 🌟",
        "كرمال نكون على مستوى توقعاتك ونفيدك بالمعلومات الصح، هل أنتِ صبية أم أنتَ شاب؟",
        "من فضلك، لتسهيل تواصلنا وخدمتك بأريحية، ما هو جنسك (ذكر/أنثى)؟",
        "عزيزي/عزيزتي، لمساعدتك بشكل أفضل وأكثر تخصيصاً، ما هو جنسك؟"
    ],
    "en": [
        "To help and serve you in the best way, could you please tell us if you are male or female? 👦👧",
        "To ensure a comfortable and excellent experience, may we know if you are male or female? 🙏😊",
        "For more accurate and friendly assistance, kindly specify your gender (male/female)? 🌟",
        "To meet your expectations and provide correct information, are you a lady or a gentleman?",
        "Please, to facilitate our communication and serve you comfortably, what is your gender (male/female)?",
        "Dear client, to assist you better and more personally, what is your gender?"
    ],
    "fr": [
        "Pour pouvoir vous aider et vous servir au mieux, pourriez-vous nous dire si vous êtes un homme ou une femme ? 👦👧",
        "Pour vous assurer une expérience confortable et excellente, pouvons-nous savoir si vous êtes un homme ou une femme ? 🙏😊",
        "Pour une assistance plus précise et amicale, pourriez-vous nous indiquer votre genre (homme/femme) ? 🌟",
        "Pour répondre à vos attentes et vous fournir des informations correctes, êtes-vous une dame ou un monsieur ?",
        "S'il vous plaît, pour faciliter notre communication et vous servir confortablement, quel est votre genre (masculin/féminin) ?",
        "Cher/Chère client(e), pour mieux vous aider et de manière plus personnalisée, quel est votre genre ?"
    ],
    "franco": [
        "Kermel ne2dar nsa3edak w nfeedak bi afdal shakel, mumkin tkabbirna law sama7t iza inta chab aw inti sabieh? 👦👧",
        "La naddammenlak tajroubeh mray7a w moumayyaze, fina na3ref law 7adertak chab aw sabieh? 🙏😊",
        "La ta2deem mosa3adeh aktar de2a w wadoudiyeh, ya rit t7addidelna jinsak (chab/sabieh)? 🌟",
        "Kermel nkoun 3a moustawe tawako3atak w nfeedak bel ma3loumat el sa7, hal enti sabieh aw inta chab?",
        "Min fadlak, la tasheel tawsolna w khedmetak bi ari7iye, chou jinsak (zakar/ountha)?",
        "3azizi/azati, la mosa3adetak bi shakel afdal w aktar ta5sees, chou jinsak?"
    ]
}

# --- Keywords for Training Mode Commands ---
SAVE_KEYWORDS = [
    "احفظ", "حفظ", "سيف", "تمام", "ok", "خلاص", "تخزين", "اعتمد", "save", "confirm", "store", "accept", "done",
    "enregistrer", "confirmer", "sauvegarder", "c'est bon", "okey", "احفظ هذا", "احفظها"
]

GENERATE_QA_KEYWORDS = [
    "سؤال وجواب", "qa", "question answer", "صيغ سؤال وجواب", "generate qa", "cree question reponse", "questions reponses",
    "سؤال و جواب", "اسئله واجوبه", "Q and A"
]

SUMMARIZE_QA_KEYWORDS = [
    "لخص", "شو اتفقنا", "ملخص", "تلخيص", "summarize", "recap", "recapituler", "show summary", "give summary",
    "kif fina n7afza", "how to save this", "comment sauvegarder ceci"
]

# --- Bot Knowledge Base (Loaded from files) ---
PRICE_LIST = ""
BOT_STYLE_GUIDE = ""
CORE_KNOWLEDGE_BASE = ""
SYSTEM_PROMPT_TEMPLATE = ""
CUSTOM_TRAINING_DATA = [] # List of custom Q&A entries
CUSTOM_TRAINING_DATA_MAP = {} # Map for quick lookup of custom Q&A by (question, language)

def load_bot_assets():
    """
    Loads static bot assets (price list, style guide, knowledge base) from persistent storage.
    """
    global PRICE_LIST, BOT_STYLE_GUIDE, CORE_KNOWLEDGE_BASE, SYSTEM_PROMPT_TEMPLATE

    ensure_dirs()
    try:
        with open(PRICE_LIST_FILE, 'r', encoding='utf-8') as f:
            PRICE_LIST = f.read().strip()
        print("✅ تم تحميل قائمة الأسعار من " + str(PRICE_LIST_FILE))
    except FileNotFoundError:
        PRICE_LIST = "قائمة الأسعار غير متوفرة. الرجاء إبلاغ المسؤول."
        print("❌ تحذير: ملف قائمة الأسعار غير موجود. الرجاء إنشاءه.")
    except Exception as e:
        PRICE_LIST = "خطأ في تحميل قائمة الأسعار."
        print(f"❌ خطأ في تحميل قائمة الأسعار: {e}")

    try:
        with open(STYLE_GUIDE_FILE, 'r', encoding='utf-8') as f:
            BOT_STYLE_GUIDE = f.read().strip()
        print("✅ تم تحميل دليل الأسلوب من " + str(STYLE_GUIDE_FILE))
    except FileNotFoundError:
        BOT_STYLE_GUIDE = "الردود يجب أن تكون ودودة، حماسية، ومرحة، وأن تعكس خبرة واحترافية المركز."
        print("❌ تحذير: ملف دليل الأسلوب غير موجود. الرجاء إنشاءه.")
    except Exception as e:
        BOT_STYLE_GUIDE = "خطأ في تحميل دليل الأسلوب."
        print(f"❌ خطأ في تحميل دليل الأسلوب: {e}")

    try:
        with open(KNOWLEDGE_BASE_FILE, 'r', encoding='utf-8') as f:
            CORE_KNOWLEDGE_BASE = f.read().strip()
        print("✅ تم تحميل قاعدة المعرفة الأساسية من " + str(KNOWLEDGE_BASE_FILE))
    except FileNotFoundError:
        CORE_KNOWLEDGE_BASE = "خدمات الليزر: إزالة شعر وتاتو فقط. لا تقدم علاجات جلدية أخرى. مواعيد العمل من 10 صباحًا حتى 6 مساءً يومياً ما عدا الأحد (عطلة)."
        print("❌ تحذير: ملف قاعدة المعرفة غير موجود. الرجاء إنشاءه.")
    except Exception as e:
        CORE_KNOWLEDGE_BASE = "خطأ في تحميل قاعدة المعرفة الأساسية."
        print(f"❌ خطأ في تحميل قاعدة المعرفة: {e}")

    try:
        with open(SYSTEM_PROMPT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            SYSTEM_PROMPT_TEMPLATE = f.read()
        if SYSTEM_PROMPT_TEMPLATE.strip():
            print("✅ تم تحميل قالب system prompt من " + str(SYSTEM_PROMPT_TEMPLATE_FILE))
        else:
            print("ℹ️ ملف قالب system prompt فارغ. سيتم إرسال system prompt فارغ كما هو.")
    except FileNotFoundError:
        SYSTEM_PROMPT_TEMPLATE = ""
        print("ℹ️ ملف قالب system prompt غير موجود. سيتم استخدام قيمة فارغة.")
    except Exception as e:
        SYSTEM_PROMPT_TEMPLATE = ""
        print(f"❌ خطأ في تحميل قالب system prompt: {e}")

def load_training_data():
    """
    DEPRECATED: This function is no longer used.
    Q&A data is now managed through API database (qa_database_service.py)
    conversation_log.jsonl is kept for historical reference only.
    """
    global CUSTOM_TRAINING_DATA, CUSTOM_TRAINING_DATA_MAP
    CUSTOM_TRAINING_DATA.clear()
    CUSTOM_TRAINING_DATA_MAP.clear()
    
    print("ℹ️ load_training_data() is deprecated - Q&A now managed via API database")
    # Do NOT load conversation_log.jsonl anymore
    # All Q&A is handled by qa_database_service.py (API-based)

# --- Initialize Bot Assets on startup ---
load_bot_assets()
# load_training_data()  # DISABLED - No longer needed, Q&A is API-based
