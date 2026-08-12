"""Language, notifications, tokens, training logs, QA translation."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

import config

_log = logging.getLogger(__name__)


# Initialize OpenAI client safely
try:
    if config.OPENAI_API_KEY:
        client: AsyncOpenAI | None = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    else:
        client = None
        print("⚠️  WARNING: OPENAI_API_KEY not set - LLM features disabled")
except Exception as e:
    client = None
    print(f"⚠️  WARNING: Failed to initialize OpenAI client: {e}")


def detect_language(text: str) -> dict:
    """
    Simple language detection for system-generated messages only.
    GPT handles language detection for user conversations.
    This is only used for error messages, rate limits, etc.
    """
    if not text or not text.strip():
        return {"language": "en", "confidence": 0.0}

    text = text.strip()

    # Count Arabic characters
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    text_length = len(text.replace(" ", ""))

    arabic_ratio = arabic_chars / text_length if text_length > 0 else 0

    # Arabic detection (50%+ Arabic characters)
    if arabic_ratio >= 0.5:
        return {"language": "ar", "confidence": arabic_ratio}

    # Simple French detection for common greetings/words
    text_lower = text.lower()
    french_indicators = ["bonjour", "merci", "je ", "vous", "oui", "non", "comment"]
    if any(word in text_lower for word in french_indicators):
        return {"language": "fr", "confidence": 0.7}

    # Default to English
    return {"language": "en", "confidence": 0.5}

def notify_human_on_whatsapp(
    user_name: Any, user_gender: Any, message_content: Any, type_of_notification: Any = "عام"
) -> None:
    """
    Logs a notification and (in a full WhatsApp integration) would send a WhatsApp message to admin/staff.
    The actual sending via WhatsApp API must be done by the caller (e.g., in main.py or handlers)
    which has access to the send_whatsapp_message function.
    """
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[{current_time_str}] NOTIFY WHATSAPP: {type_of_notification} - From: {user_name} ({user_gender}) - Message: {message_content}"
    )
    # To actually send a WhatsApp message here, main.py's send_whatsapp_message function
    # would need to be passed down or made globally accessible.
    # For now, it logs and the handler (e.g., text_handlers) will explicitly call send_whatsapp_message
    # to the WHATSAPP_TO number from config.
    # The existing calls in text_handlers.py and photo_handlers.py already handle the actual sending.
    print(f"Would send WhatsApp notification to {config.WHATSAPP_TO} (defined in .env).")

def count_tokens(text: Any) -> Any:
    if not text:
        return 0
    return len(text.split())

def save_for_training_conversation_log(user_message: Any, bot_response: Any) -> None:
    log_entry = {
        "question": user_message,
        "answer": bot_response,
        "language": detect_language(user_message)["language"],
        "timestamp": str(datetime.datetime.now()),
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/conversation_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            f.flush()
    except Exception as e:
        print(f"❌ خطأ في حفظ سجل التدريب: {e}. قد تكون مشكلة أذونات أو مسار.")
        import traceback

        traceback.print_exc()

async def translate_qa_pair_with_gpt(question: str, answer: str, target_languages: list) -> Any:
    """
    Translates a question/answer pair into target languages.
    Franco answer language will remain Arabic.
    """
    if not question or not answer:
        return []

    lang_map = {"ar": "Arabic", "en": "English", "fr": "French", "franco": "Franco Arabic"}

    translations = []

    # Standard translations (ar, en, fr)
    standard_target_languages = [lang for lang in target_languages if lang != "franco"]
    if standard_target_languages:
        standard_target_langs_str = ", ".join(
            [f"'{l_code}' ({lang_map.get(l_code, l_code)})" for l_code in standard_target_languages]
        )

        system_instruction_standard_translation = (
            "You are a highly accurate translator specializing in formulating questions and answers for a customer service bot. "
            f"Your task is to precisely translate the provided question and answer into the following languages: {standard_target_langs_str}. "
            "Maintain the original context and tone, suitable for a beauty/laser center customer service bot. "
            "The response MUST be in strict JSON format (a list of {{question, answer, language}} objects)."
            "**Required Example:**\n"
            "```json\n"
            "[\n"
            '  {{"question": "What laser hair removal services do you offer?", "answer": "We offer advanced laser hair removal services using the latest technology to ensure optimal results. For a free consultation, you can book an appointment.", "language": "en"}}\n'
            "]\n"
            "```\n"
            "Provide answers only within the specified JSON. Do not add any other text outside the JSON."
        )

        messages_standard = [
            {"role": "system", "content": system_instruction_standard_translation},
            {"role": "user", "content": f"Original Question: {question}\nOriginal Answer: {answer}"},
        ]

        try:
            if client is None:
                raise RuntimeError("OpenAI client is not configured")
            response_standard = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=cast(list[ChatCompletionMessageParam], messages_standard),
                response_format={"type": "json_object"},
            )
            if not response_standard.choices:
                raise ValueError("GPT returned no choices")
            content = response_standard.choices[0].message.content or ""
            parsed_data_standard = json.loads(content.strip())
            if isinstance(parsed_data_standard, list):
                translations.extend(parsed_data_standard)
        except Exception as e:
            print(f"❌ ERROR in standard translation: {e}")
            pass

    # Translation to Franco Arabic (specific: Franco question, Arabic answer)
    if "franco" in target_languages:
        system_instruction_franco_translation = (
            "You are a highly accurate translator specializing in formulating questions and answers for a customer service bot. "
            "Your task is to precisely translate the original question into **Franco Arabic (franco)**, "
            "while keeping the **original answer as is in Arabic**. "
            "For Franco Arabic, use Latin characters to write Arabic words (e.g., 'kifak', 'shou'). Be creative in formulating colloquial Lebanese Franco. "
            "The response **MUST be in strict JSON format** (a single {{question, answer, language}} object)."
            "**Required Example:**\n"
            "```json\n"
            '{{"question": "Sho sa3at 3amal al markaz?", "answer": "ساعات عمل مركز لينا ليزر هي من 10 صباحاً لـ 6 مساءً يومياً ما عدا الأحد.", "language": "franco"}}\n'
            "```\n"
            "Return only the JSON. Do not add any other text outside the JSON."
        )
        messages_franco = [
            {"role": "system", "content": system_instruction_franco_translation},
            {"role": "user", "content": f"Original Question: {question}\nOriginal Answer (Arabic): {answer}"},
        ]
        try:
            if client is None:
                raise RuntimeError("OpenAI client is not configured")
            response_franco = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=cast(list[ChatCompletionMessageParam], messages_franco),
                response_format={"type": "json_object"},
            )
            if not response_franco.choices:
                raise ValueError("GPT returned no choices")
            content = response_franco.choices[0].message.content or ""
            parsed_data_franco = json.loads(content.strip())
            if (
                isinstance(parsed_data_franco, dict)
                and "question" in parsed_data_franco
                and "answer" in parsed_data_franco
                and "language" in parsed_data_franco
            ):
                translations.append(parsed_data_franco)
        except Exception as e:
            print(f"❌ ERROR in franco translation: {e}")
            pass

    return translations
