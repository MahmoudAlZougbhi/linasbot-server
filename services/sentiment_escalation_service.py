"""
Sentiment Analysis & Auto-Escalation Service
Detects negative sentiment, anger, frustration, and confusion
Automatically escalates conversations to human operators when needed

Keyword catalogs: sentiment_escalation_keywords (LOC split).
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from services.sentiment_escalation_keywords import (  # noqa: F401
    ANGER_KEYWORDS,
    CLARIFICATION_KEYWORDS,
    CONFUSION_KEYWORDS,
    HUMAN_REQUEST_KEYWORDS,
    OFFENSIVE_KEYWORDS,
    URGENCY_KEYWORDS,
)


class SentimentEscalationService:
    """Service for detecting sentiment and auto-escalating to human operators"""

    ANGER_KEYWORDS = ANGER_KEYWORDS
    HUMAN_REQUEST_KEYWORDS = HUMAN_REQUEST_KEYWORDS
    CONFUSION_KEYWORDS = CONFUSION_KEYWORDS
    CLARIFICATION_KEYWORDS = CLARIFICATION_KEYWORDS
    OFFENSIVE_KEYWORDS = OFFENSIVE_KEYWORDS
    URGENCY_KEYWORDS = URGENCY_KEYWORDS

    # Repeated messages threshold
    REPETITION_THRESHOLD = 3

    def __init__(self) -> None:
        self.user_message_history: dict[str, list[dict[str, Any]]] = {}  # Track recent messages per user
        self.escalation_reasons: dict[str, dict[str, Any]] = {}  # Track why each user was escalated

    def analyze_sentiment(self, user_id: str, message: str, language: str = "ar") -> dict[str, Any]:
        """
        Analyze message sentiment and determine if escalation is needed

        Returns:
            {
                "sentiment": "positive|neutral|negative|angry",
                "should_escalate": bool,
                "escalation_reason": str,
                "confidence": float,
                "detected_issues": []
            }
        """
        message_lower = message.lower()
        detected_issues = []
        escalation_score = 0

        # Initialize user history if needed
        if user_id not in self.user_message_history:
            self.user_message_history[user_id] = []

        # Add current message to history
        self.user_message_history[user_id].append({"message": message, "timestamp": datetime.datetime.now()})

        # Keep only last 10 messages
        if len(self.user_message_history[user_id]) > 10:
            self.user_message_history[user_id] = self.user_message_history[user_id][-10:]

        # 1. Human request: AI (GPT) detects from CONTEXT - no keyword matching here.

        # 2. Check for anger/offensive language
        anger_found = self._check_keywords(message_lower, self.ANGER_KEYWORDS, language)
        offensive_found = self._check_keywords(message_lower, self.OFFENSIVE_KEYWORDS, language)

        if offensive_found:
            detected_issues.append("offensive_language")
            escalation_score += 80
            print(f"🚨 ESCALATION: User ...{str(user_id)[-4:]} used offensive language")
        elif anger_found:
            detected_issues.append("anger_detected")
            escalation_score += 60
            print(f"⚠️ WARNING: User ...{str(user_id)[-4:]} showing signs of anger")

        # 3. Check for confusion/frustration
        confusion_found = self._check_keywords(message_lower, self.CONFUSION_KEYWORDS, language)
        if confusion_found:
            detected_issues.append("confusion_detected")
            escalation_score += 40
            print(f"⚠️ WARNING: User ...{str(user_id)[-4:]} seems confused")

        # 4. Check for urgency
        urgency_found = self._check_keywords(message_lower, self.URGENCY_KEYWORDS, language)
        if urgency_found:
            detected_issues.append("urgency_detected")
            escalation_score += 30
            print(f"⚠️ WARNING: User ...{str(user_id)[-4:]} indicated urgency")

        # 5. Check for message repetition (user keeps asking same thing)
        repetition_score = self._check_repetition(user_id, message)
        if repetition_score >= self.REPETITION_THRESHOLD:
            detected_issues.append("message_repetition")
            escalation_score += 50
            print(f"⚠️ WARNING: User ...{str(user_id)[-4:]} repeating messages ({repetition_score} times)")

        # 6. Check for excessive punctuation (!!!, ???)
        if self._check_excessive_punctuation(message):
            detected_issues.append("excessive_punctuation")
            escalation_score += 20
            print(f"⚠️ WARNING: User ...{str(user_id)[-4:]} using excessive punctuation")

        # 7. Check for ALL CAPS (shouting)
        if self._check_all_caps(message):
            detected_issues.append("all_caps")
            escalation_score += 25
            print(f"⚠️ WARNING: User ...{str(user_id)[-4:]} using ALL CAPS")

        # Determine sentiment
        if escalation_score >= 80:
            sentiment = "angry"
        elif escalation_score >= 40:
            sentiment = "negative"
        elif escalation_score >= 20:
            sentiment = "neutral"
        else:
            sentiment = "positive"

        # Determine if escalation is needed (anger/frustration/confusion → transfer)
        should_escalate = escalation_score >= 50

        # Determine escalation reason
        escalation_reason = self._get_escalation_reason(detected_issues)

        # Store escalation reason
        if should_escalate:
            self.escalation_reasons[user_id] = {
                "reason": escalation_reason,
                "score": escalation_score,
                "issues": detected_issues,
                "timestamp": datetime.datetime.now(),
            }

        confidence = min(escalation_score / 100, 1.0)

        result: dict[str, Any] = {
            "sentiment": sentiment,
            "should_escalate": should_escalate,
            "escalation_reason": escalation_reason,
            "confidence": confidence,
            "escalation_score": escalation_score,
            "detected_issues": detected_issues,
        }

        print(
            f"📊 Sentiment Analysis for ...{str(user_id)[-4:]}: sentiment={result.get('sentiment') if isinstance(result, dict) else type(result).__name__}"
        )

        return result

    def _check_keywords(self, message: str, keyword_dict: dict, language: str) -> bool:
        """Check if message contains any keywords from the dictionary"""
        keywords = list(keyword_dict.get(language, []))
        # Also check English keywords as fallback
        if language != "en":
            keywords.extend(keyword_dict.get("en", []))
        # For Arabic, also check Franco-Arabic (Lebanese often mix)
        if language == "ar":
            keywords.extend(keyword_dict.get("franco", []))
        # For Franco, also check Arabic-script keywords because users often mix both.
        if language == "franco":
            keywords.extend(keyword_dict.get("ar", []))
        # For offensive language: ALWAYS check franco (users mix English/Arabic with Franco insults)
        if keyword_dict is self.OFFENSIVE_KEYWORDS and "franco" in keyword_dict:
            keywords.extend(keyword_dict.get("franco", []))

        for keyword in keywords:
            # Use word boundaries to avoid substring matches (e.g., "bad" in "bade")
            # This prevents false positives like "bade" (I want) triggering "bad" (anger)
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, message, re.IGNORECASE):
                return True
        # For offensive: also match elongated variants (5arahhhh, kharaaa, etc.)
        if keyword_dict is self.OFFENSIVE_KEYWORDS:
            message_lower = message.lower()
            for base in ("5ara", "khara", "kol hawa", "kol 5ara", "kol khara"):
                if base in message_lower:
                    # Match base + optional repeated chars (5arahhhh, etc.)
                    flexible = r"\b" + re.escape(base) + r"[a-zA-Z0-9]*\b"
                    if re.search(flexible, message, re.IGNORECASE):
                        return True
        return False

    def _check_repetition(self, user_id: str, current_message: str) -> int:
        """Check how many times user has sent similar messages"""
        if user_id not in self.user_message_history:
            return 0

        recent_messages = self.user_message_history[user_id][-5:]  # Last 5 messages
        current_lower = current_message.lower().strip()

        repetition_count = 0
        for msg_data in recent_messages:
            prev_message = msg_data["message"].lower().strip()
            # Check for exact match or very similar (>80% similarity)
            if current_lower == prev_message or self._similarity(current_lower, prev_message) > 0.8:
                repetition_count += 1

        return repetition_count

    def _similarity(self, str1: str, str2: str) -> float:
        """Calculate simple similarity between two strings"""
        if not str1 or not str2:
            return 0.0

        # Simple word-based similarity
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def _check_excessive_punctuation(self, message: str) -> bool:
        """Check for excessive punctuation marks (!!!, ???, etc.)"""
        # Count consecutive punctuation
        exclamation_count = len(re.findall(r"!{2,}", message))
        question_count = len(re.findall(r"\?{2,}", message))

        return exclamation_count > 0 or question_count > 0

    def _check_all_caps(self, message: str) -> bool:
        """Check if message is mostly in ALL CAPS"""
        # Remove non-alphabetic characters
        letters = [c for c in message if c.isalpha()]

        if len(letters) < 5:  # Too short to judge
            return False

        caps_count = sum(1 for c in letters if c.isupper())
        caps_ratio = caps_count / len(letters)

        return caps_ratio > 0.7  # More than 70% caps

    def _get_escalation_reason(self, detected_issues: list) -> str:
        """Get human-readable escalation reason"""
        if "explicit_human_request" in detected_issues:
            return "customer_requested_human"
        elif "offensive_language" in detected_issues:
            return "offensive_language_detected"
        elif "anger_detected" in detected_issues:
            return "customer_angry"
        elif "message_repetition" in detected_issues:
            return "bot_unable_to_help"
        elif "confusion_detected" in detected_issues:
            return "customer_confused"
        elif "urgency_detected" in detected_issues:
            return "urgent_request"
        elif "excessive_punctuation" in detected_issues or "all_caps" in detected_issues:
            return "customer_frustrated"
        else:
            return "negative_sentiment_detected"

    def get_escalation_info(self, user_id: str) -> dict[str, Any] | None:
        """Get escalation information for a user"""
        return self.escalation_reasons.get(user_id)

    def clear_user_history(self, user_id: str) -> None:
        """Clear history for a user (e.g., after conversation ends)"""
        if user_id in self.user_message_history:
            del self.user_message_history[user_id]
        if user_id in self.escalation_reasons:
            del self.escalation_reasons[user_id]


# Global instance
sentiment_service = SentimentEscalationService()
