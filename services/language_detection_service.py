# services/language_detection_service.py
"""
Language Detection Service - Wraps language_resolver.py
Detects language BEFORE GPT call on each message
"""

import json
import re
from typing import Dict, List, Optional

from language_resolver import LanguageResolver, system_language_instruction
from services.user_persistence_service import user_persistence
from services.llm_core_service import client as openai_client


SUPPORTED_TRAINING_LANGUAGES = {"ar", "en", "fr", "franco"}
FRENCH_MARKERS = ("bonjour", "merci", "salut", "s'il", "vous", "comment")
FRANCO_MARKERS = (
    "kif",
    "kifak",
    "kifik",
    "shou",
    "shu",
    "mish",
    "mafi",
    "3",
    "7",
    "2",
    "9",
)


class LanguageDetectionService:
    def __init__(self):
        self._resolver = LanguageResolver()

    def detect_language(
        self,
        user_id: str,
        message: str,
        user_data: dict,
        is_expecting_name: bool = False
    ) -> dict:
        """
        Detect language from message text.

        Args:
            user_id: The user's WhatsApp ID
            message: The user's message text
            user_data: User data dict containing conversation_id etc.
            is_expecting_name: If True, skip language detection (name input)

        Returns:
            dict with:
            - detected_language: 'ar', 'en', 'fr', 'franco' (what user wrote in)
            - response_language: 'ar', 'en', 'fr' (what bot should respond in)
            - system_instruction: GPT prompt instruction for this language
            - skipped: bool (True if detection was skipped)
        """
        conversation_id = user_data.get('current_conversation_id', user_id)

        # Set expecting_full_name flag if needed
        if is_expecting_name:
            self._resolver.set_expecting_full_name(conversation_id, True)

        # Detect language
        detected = self._resolver.resolve(
            conversation_id=conversation_id,
            user_text=message,
            accept_language=None,
            user_lang_override=None
        )

        # Map franco to ar for response (user writes franco, bot responds Arabic script)
        response_lang = 'ar' if detected == 'franco' else detected

        # Save to user persistence
        user_persistence.save_user_language(user_id, detected)

        return {
            'detected_language': detected,
            'response_language': response_lang,
            'system_instruction': system_language_instruction(response_lang),
            'skipped': False
        }

    def set_expecting_name(self, user_id: str, user_data: dict, expecting: bool) -> None:
        """Set flag to ignore language detection on next message (for name input)"""
        conversation_id = user_data.get('current_conversation_id', user_id)
        self._resolver.set_expecting_full_name(conversation_id, expecting)

    def get_resolver(self) -> LanguageResolver:
        """Get the underlying resolver for direct access if needed"""
        return self._resolver

    @staticmethod
    def normalize_training_language(language: Optional[str], default: str = "ar") -> str:
        """
        Normalize language identifiers to project-standard codes.
        """
        if not language:
            return default
        normalized = str(language).strip().lower()
        alias_map = {
            "arabic": "ar",
            "english": "en",
            "french": "fr",
            "francoarabic": "franco",
            "franco-arabic": "franco",
            "franco_arabic": "franco",
        }
        normalized = alias_map.get(normalized, normalized)
        if normalized not in SUPPORTED_TRAINING_LANGUAGES:
            return default
        return normalized

    def detect_training_language(self, text: str) -> str:
        """
        Lightweight language detection for training Q&A records.
        """
        text = (text or "").strip()
        if not text:
            return "ar"

        if re.search(r"[\u0600-\u06FF]", text):
            return "ar"

        lowered = text.lower()
        if any(marker in lowered for marker in FRENCH_MARKERS):
            return "fr"

        if any(marker in lowered for marker in FRANCO_MARKERS):
            return "franco"

        return "en"

    async def translate_arabic_training_pair(
        self,
        question_ar: str,
        answer_ar: str,
        target_languages: Optional[List[str]] = None,
    ) -> Dict:
        """
        Translate Arabic Q&A into EN/FR/Franco for training storage.
        """
        target_languages = target_languages or ["en", "fr", "franco"]
        normalized_targets = []
        for lang in target_languages:
            normalized = self.normalize_training_language(lang, default="")
            if normalized and normalized != "ar" and normalized not in normalized_targets:
                normalized_targets.append(normalized)

        if not question_ar or not answer_ar or not normalized_targets:
            return {"success": False, "translations": {}, "missing_languages": normalized_targets}

        prompt = (
            "You are an expert translator for a laser clinic customer-service bot.\n"
            "Translate the Arabic question and answer into requested target languages.\n"
            "Return strict JSON object only.\n"
            "JSON shape:\n"
            "{\n"
            '  "en": {"question": "...", "answer": "..."},\n'
            '  "fr": {"question": "...", "answer": "..."},\n'
            '  "franco": {"question": "...", "answer": "..."}\n'
            "}\n"
            "Rules:\n"
            "- Keep meaning and details unchanged.\n"
            "- Franco must be Lebanese Arabic written with Latin characters.\n"
            "- Franco answer must also be Latin-script Franco (no Arabic script).\n"
            "- Do not include markdown or extra keys."
        )

        user_payload = {
            "question_ar": question_ar,
            "answer_ar": answer_ar,
            "target_languages": normalized_targets,
        }

        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
            )
            content = response.choices[0].message.content.strip() if response.choices else "{}"
            parsed = json.loads(content)
        except Exception as error:
            print(f"❌ translate_arabic_training_pair failed: {error}")
            return {
                "success": False,
                "translations": {},
                "missing_languages": normalized_targets,
                "error": str(error),
            }

        translations: Dict[str, Dict[str, str]] = {}
        for lang in normalized_targets:
            lang_payload = parsed.get(lang, {})
            question = str(lang_payload.get("question", "")).strip()
            answer = str(lang_payload.get("answer", "")).strip()
            if question and answer:
                translations[lang] = {"question": question, "answer": answer}

        missing = [lang for lang in normalized_targets if lang not in translations]
        return {
            "success": len(missing) == 0,
            "translations": translations,
            "missing_languages": missing,
        }


# Global singleton
language_detection_service = LanguageDetectionService()
