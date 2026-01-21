# services/language_detection_service.py
"""
Language Detection Service - Wraps language_resolver.py
Detects language BEFORE GPT call on each message
"""

from language_resolver import LanguageResolver, system_language_instruction
from services.user_persistence_service import user_persistence


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


# Global singleton
language_detection_service = LanguageDetectionService()
