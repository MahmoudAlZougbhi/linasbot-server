# -*- coding: utf-8 -*-
"""
Dynamic Messages Service

Stores editable bot dynamic messages (with usage conditions) in persistent settings.
Used by Content Manager to let operators inspect/edit runtime wording.
"""

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any

from storage.persistent_storage import SETTINGS_DIR


DYNAMIC_MESSAGES_FILE = SETTINGS_DIR / "dynamic_messages.json"


DEFAULT_DYNAMIC_MESSAGES: Dict[str, Dict[str, Any]] = {
    "router_greeting": {
        "label": "Router Greeting",
        "when_used": "Sent when user message is greeting-only and there is no pending state.",
        "messages": {
            "ar": "مرحباً! 😊 أنا مروى المساعدة الذكية من مركز لينا ليزر 🌷 كيف فيني أساعدك اليوم؟",
            "en": "Hello! 😊 I'm Marwa, the smart assistant from Lina's Laser Center 🌷 How can I help you today?",
            "fr": "Bonjour ! 😊 Je suis Marwa, l'assistante intelligente de Lina's Laser Center 🌷 Comment puis-je vous aider aujourd'hui ?",
            "franco": "مرحباً! 😊 أنا مروى المساعدة الذكية من مركز لينا ليزر 🌷 كيف فيني أساعدك اليوم؟",
        },
    },
    "router_fallback": {
        "label": "Router Fallback",
        "when_used": "Sent when router cannot determine a safe intent.",
        "messages": {
            "ar": "أكيد، فيك توضحلي أكتر شو الخدمة أو الموضوع اللي بدك تستفسر عنه؟",
            "en": "Sure, could you tell me more about which service or topic you'd like to know about?",
            "fr": "Bien sûr, pourriez-vous préciser quel service ou sujet vous intéresse ?",
            "franco": "أكيد، فيك توضحلي أكتر شو الخدمة أو الموضوع اللي بدك تستفسر عنه؟",
        },
    },
    "router_ask_clarification": {
        "label": "Ask Clarification",
        "when_used": "Sent when user request is too vague and missing required detail (service/topic).",
        "messages": {
            "ar": "أكيد، لأي خدمة بدك الأسعار أو المعلومات؟ (ليزر شعر، إزالة وشم، تبييض، إلخ)",
            "en": "Sure! Which service would you like prices or information about? (hair removal, tattoo removal, whitening, etc.)",
            "fr": "Bien sûr ! Pour quel service souhaitez-vous des prix ou des informations ? (épilation, tatouage, blanchiment, etc.)",
            "franco": "أكيد، لأي خدمة بدك الأسعار أو المعلومات؟ (ليزر شعر، إزالة وشم، تبييض، إلخ)",
        },
    },
    "session_greeting_after_inactivity": {
        "label": "Session Greeting (Inactivity)",
        "when_used": "Sent at session start for new conversation or after long inactivity window.",
        "messages": {
            "ar": "مرحباً! 😊 كيف فيني ساعدك اليوم؟",
            "en": "Hello! 😊 How can I help you today?",
            "fr": "Bonjour ! 😊 Comment puis-je vous aider aujourd'hui ?",
            "franco": "Marhaba! 😊 kif fini se3dik el yom?",
        },
    },
    "human_handover_message": {
        "label": "Human Handover Message",
        "when_used": "Sent when user requests a human or escalation requires handover.",
        "messages": {
            "ar": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏",
            "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏",
            "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏",
            "franco": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏",
        },
    },
    "waiting_queue_message": {
        "label": "Waiting Queue Message",
        "when_used": "Sent while human takeover is active and no operator assigned yet.",
        "messages": {
            "ar": "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏",
            "en": "Just a moment, we'll be with you shortly. Thank you for your patience 🙏",
            "fr": "Un instant, nous serons avec vous sous peu. Merci pour votre patience 🙏",
            "franco": "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏",
        },
    },
}


def _ensure_parent_dir() -> None:
    Path(SETTINGS_DIR).mkdir(parents=True, exist_ok=True)


def _read_file() -> Dict[str, Any]:
    _ensure_parent_dir()
    if not Path(DYNAMIC_MESSAGES_FILE).exists():
        return {}
    try:
        with open(DYNAMIC_MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_file(data: Dict[str, Any]) -> None:
    _ensure_parent_dir()
    with open(DYNAMIC_MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_dynamic_messages_catalog() -> Dict[str, Any]:
    """Return merged catalog: defaults + persisted overrides."""
    merged = deepcopy(DEFAULT_DYNAMIC_MESSAGES)
    stored = _read_file()
    for key, value in stored.items():
        if key not in merged:
            continue
        if isinstance(value, dict):
            if isinstance(value.get("label"), str):
                merged[key]["label"] = value["label"]
            if isinstance(value.get("when_used"), str):
                merged[key]["when_used"] = value["when_used"]
            msgs = value.get("messages")
            if isinstance(msgs, dict):
                for lang in ("ar", "en", "fr", "franco"):
                    if isinstance(msgs.get(lang), str) and msgs.get(lang).strip():
                        merged[key]["messages"][lang] = msgs[lang]
    return merged


def update_dynamic_messages_catalog(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update persisted overrides from API payload and return merged catalog."""
    if not isinstance(payload, dict):
        return get_dynamic_messages_catalog()
    current = get_dynamic_messages_catalog()
    for key, item in payload.items():
        if key not in current or not isinstance(item, dict):
            continue
        if isinstance(item.get("label"), str):
            current[key]["label"] = item["label"]
        if isinstance(item.get("when_used"), str):
            current[key]["when_used"] = item["when_used"]
        msgs = item.get("messages")
        if isinstance(msgs, dict):
            for lang in ("ar", "en", "fr", "franco"):
                if isinstance(msgs.get(lang), str):
                    current[key]["messages"][lang] = msgs[lang]
    _write_file(current)
    return current


def get_dynamic_message(key: str, lang: str = "ar") -> str:
    """Get one dynamic message by key/language with safe fallback."""
    catalog = get_dynamic_messages_catalog()
    item = catalog.get(key) or {}
    msgs = item.get("messages") or {}
    lang_key = (lang or "ar").lower()
    message = (
        msgs.get(lang_key)
        or msgs.get("ar")
        or ""
    )
    if lang_key in ("ar", "franco"):
        # Keep Arabic-facing runtime messages in Arabic script for known assistant/brand names.
        replacements = {
            "Marwa AI Assistant": "مروى",
            "Marwa": "مروى",
            "Lina’s Laser Center": "مركز لينا ليزر",
            "Lina's Laser Center": "مركز لينا ليزر",
            "Lina’s Laser": "لينا ليزر",
            "Lina's Laser": "لينا ليزر",
            "مركز ليناس ليزر": "مركز لينا ليزر",
            "ليناس ليزر": "لينا ليزر",
        }
        for latin_text, arabic_text in replacements.items():
            message = message.replace(latin_text, arabic_text)

        # Normalize accidental mixed-script leftovers around brand naming.
        message = re.sub(r"\bLina(?:['’]s)?\b", "لينا", message, flags=re.IGNORECASE)
        message = re.sub(r"\bLaser\b", "ليزر", message, flags=re.IGNORECASE)
    return message
