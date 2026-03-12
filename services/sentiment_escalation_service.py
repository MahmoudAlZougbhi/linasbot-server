# -*- coding: utf-8 -*-
"""
Sentiment Analysis & Auto-Escalation Service
Detects negative sentiment, anger, frustration, and confusion
Automatically escalates conversations to human operators when needed
"""

import re
from typing import Dict, Any, Optional
import datetime


class SentimentEscalationService:
    """Service for detecting sentiment and auto-escalating to human operators"""
    
    # Anger/frustration indicators in multiple languages
    ANGER_KEYWORDS = {
        "ar": [
            "غاضب", "زعلان", "مستاء", "منزعج", "متضايق", "مش راضي",
            "مش مبسوط", "مش عاجبني", "مش قابل", "مش معقول",
            "يا حرام", "يا خسارة", "فاشل", "سيء", "وحش", "مش كويس",
            "مش منيح", "بدي شكي", "بدي اشتكي", "شكوى", "مشكلة كبيرة",
            "ما بينفع", "مش نافع", "عصبي", "زعلان", "زعلانة",
            # Franco-Arabic frustration
            "ze3len", "ze3lane", "3asab", "3asabe", "balash", "blaash",
            "sho bek", "shu bek", "sho elak", "ma fehem", "ma fhem",
            "ta3ebetni", "ta3ebtni", "ze3letni", "3asabni"
        ],
        "en": [
            "angry", "mad", "furious", "upset", "frustrated", "annoyed",
            "irritated", "disappointed", "terrible", "awful", "horrible",
            "worst", "bad", "poor", "unacceptable", "ridiculous",
            "complaint", "complain", "problem", "issue", "not happy",
            "not satisfied", "dissatisfied", "fed up", "sick of"
        ],
        "fr": [
            "fâché", "en colère", "furieux", "mécontent", "frustré",
            "agacé", "irrité", "déçu", "terrible", "horrible", "mauvais",
            "pire", "inacceptable", "ridicule", "plainte", "problème",
            "pas content", "pas satisfait", "insatisfait"
        ]
    }
    
    # Demanding human operator keywords (Arabic + Franco-Arabic / Lebanese)
    HUMAN_REQUEST_KEYWORDS = {
        "ar": [
            "بدي احكي مع حدا", "بدي موظف", "بدي شخص", "بدي انسان",
            "وديني على موظف", "حولني على موظف", "بدي مدير", "بدي مسؤول",
            "مش بدي بوت", "مش بدي روبوت", "بدي حدا بشري", "بدي حدا حقيقي",
            "ما بدي معك", "بدي غيرك", "بدي حدا تاني", "بدي حدا يساعدني",
            "موظف خدمة عملاء", "خدمة العملاء", "بدي اشتكي", "بدي شكوى",
            "بدي احكي مع موظف", "بدي احكي مع انسان", "بدي احكي مع حدا بشري",
            "عايز اكلم حد", "عايز اتكلم مع حد", "عايز موظف", "عايز انسان",
            "اريد موظف", "اريد انسان", "اريد التحدث مع موظف", "اريد التحدث مع انسان",
            "بدّي موظف", "بدّي إنسان", "بدّي احكي مع موظف", "بدّي احكي مع انسان",
            "حابب احكي مع موظف", "نفسي احكي مع حدا", "لو سمحت بدي موظف",
            "حولوني على موظف", "وصلوني لموظف", "في حدا يحكي معي",
            # Franco-Arabic / Lebanese colloquial
            "bede mwzaf", "bede mwazzaf", "bede hada ye7kine", "bede hada ye7ke",
            "hada ye7ke ma3e", "hada ye7kine", "bede hada ye7ke ma3e",
            "ye7ke ma3e", "hada ye7ke ma3i", "bede hada ehke ma3o",
            "bede hada y7kine", "hada y7ke ma3e", "bede hada y7ke ma3e",
            "i need human", "need human", "want human", "bede human"
        ],
        "en": [
            "speak to someone", "talk to someone", "human", "real person",
            "transfer me", "connect me", "operator", "agent", "representative",
            "customer service", "manager", "supervisor", "not a bot",
            "real human", "actual person", "someone else", "help me",
            "complaint", "complain", "escalate", "live agent", "human agent",
            "speak to an agent", "talk to an agent", "connect me to an agent",
            "i need human", "need human", "want human"
        ],
        "franco": [
            "bede mwzaf", "bede mwazzaf", "bede hada ye7kine", "bede hada ye7ke",
            "hada ye7ke ma3e", "hada ye7kine", "bede hada ye7ke ma3e",
            "ye7ke ma3e", "hada ye7ke ma3i", "bede hada ehke ma3o",
            "bede hada y7kine", "hada y7ke ma3e", "bede hada y7ke ma3e",
            "i need human", "need human", "want human", "bede human"
        ],
        "fr": [
            "parler à quelqu'un", "personne réelle", "humain", "opérateur",
            "agent", "représentant", "service client", "responsable",
            "pas un bot", "vraie personne", "quelqu'un d'autre",
            "plainte", "se plaindre", "agent humain", "parler à un agent"
        ]
    }
    
    # Confusion/frustration indicators (triggers escalation when combined)
    CONFUSION_KEYWORDS = {
        "ar": [
            "مش فاهم", "ما فهمت", "مش واضح", "مش مفهوم", "معقد",
            "صعب", "مش عارف", "ما بعرف", "مش قادر", "تعبتني",
            "كتير معقد", "مش بسيط", "مش سهل", "محتار", "ضايع",
            "مش عم بفهم", "ما عم بفهم", "شو يعني", "كيف يعني",
            # Franco-Arabic
            "ma fehem", "ma fhem", "mish fahm", "shu 3am te2oul",
            "mish wade7"
        ],
        "en": [
            "don't understand", "not clear", "confusing", "confused",
            "complicated", "difficult", "hard", "can't figure",
            "makes no sense", "doesn't make sense", "what do you mean",
            "i don't get it", "lost", "stuck", "frustrated"
        ],
        "fr": [
            "ne comprends pas", "pas clair", "confus", "compliqué",
            "difficile", "je ne comprends pas", "qu'est-ce que",
            "ça n'a pas de sens", "perdu", "bloqué"
        ]
    }

    CLARIFICATION_KEYWORDS = {
        "ar": [
            "وضحلي", "فسرلي", "شرحلي", "اشرح", "فسر", "وضح",
            "شو قصدك", "شو يعني", "شو المقصود", "مش واضح",
            "ما فهمت", "مش فاهم", "وضح سؤالك"
        ],
        "en": [
            "explain", "clarify", "what do you mean", "not clear",
            "i don't understand", "i dont understand", "can you explain"
        ],
        "fr": [
            "explique", "clarifie", "je ne comprends pas", "pas clair",
            "qu'est-ce que tu veux dire"
        ]
    }
    
    # Profanity/offensive language (mild detection)
    OFFENSIVE_KEYWORDS = {
        "ar": [
            "غبي", "احمق", "أحمق", "تافه", "سخيف", "وسخ", "قذر", "حقير",
            "خرا", "خرة", "زبالة", "ابن الكلب", "يا كلب", "تفو", "يلعن", "لعنة",
            "عير", "عيركم", "بهيم", "بهائم", "ما فهم", "مفهم"
        ],
        "en": [
            "stupid", "idiot", "dumb", "useless", "garbage", "trash",
            "crap", "suck", "sucks", "moron", "fool", "asshole", "dick",
            "shit", "bullshit", "damn you", "screw you", "fuck", "fucking",
            "piece of shit", "motherfucker", "bastard", "sucker"
        ],
        "fr": [
            "stupide", "idiot", "nul", "débile", "pourri", "con", "connard",
            "merde", "putain", "enculé", "salope", "crétin", "imbécile",
            "dégage", "va te faire", "ferme ta gueule", "ta gueule"
        ],
        "franco": [
            "5ara", "khara", "kol hawa", "kell hawa", "koul hawa",
            "kol 5ara", "kol khara", "zbele", "zbale",
            "ya kalb", "ibn kalb", "tfou", "yl3an", "3alek", "3layk", "3alayk",
            "ahbal", "a7bal", "hmar", "7mar", "kalb", "zbaleh", "zbeleh",
            "manyk", "emak", "e5tak", "e5t", "bhim", "bala fhem", "ma fhem",
            "eyre", "eyreh", "eyre fikon", "eyreh fikon", "m2yra", "ma3e",
            "kiss emak", "kiss e5tak", "bala fhem", "mafhem",
            "le heak", "le heak sar", "le7ak", "le7e2", "sir 3al", "sir 3alek", "sir 3layk",
        ],
    }
    
    # Urgency indicators
    URGENCY_KEYWORDS = {
        "ar": [
            "عاجل", "ضروري", "مستعجل", "سريع", "بسرعة", "حالاً",
            "فوراً", "الآن", "هلق", "دلوقتي", "مهم", "مهم جداً",
            "طارئ", "emergency", "urgent"
        ],
        "en": [
            "urgent", "emergency", "asap", "immediately", "right now",
            "quickly", "fast", "important", "critical", "serious"
        ],
        "fr": [
            "urgent", "urgence", "immédiatement", "tout de suite",
            "rapidement", "vite", "important", "critique", "sérieux"
        ]
    }
    
    # Repeated messages threshold
    REPETITION_THRESHOLD = 3
    
    def __init__(self):
        self.user_message_history = {}  # Track recent messages per user
        self.escalation_reasons = {}  # Track why each user was escalated
    
    def analyze_sentiment(self, user_id: str, message: str, language: str = "ar") -> Dict[str, Any]:
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
        self.user_message_history[user_id].append({
            "message": message,
            "timestamp": datetime.datetime.now()
        })
        
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
            print(f"🚨 ESCALATION: User {user_id} used offensive language")
        elif anger_found:
            detected_issues.append("anger_detected")
            escalation_score += 60
            print(f"⚠️ WARNING: User {user_id} showing signs of anger")
        
        # 3. Check for confusion/frustration
        confusion_found = self._check_keywords(message_lower, self.CONFUSION_KEYWORDS, language)
        if confusion_found:
            detected_issues.append("confusion_detected")
            escalation_score += 40
            print(f"⚠️ WARNING: User {user_id} seems confused")
        
        # 4. Check for urgency
        urgency_found = self._check_keywords(message_lower, self.URGENCY_KEYWORDS, language)
        if urgency_found:
            detected_issues.append("urgency_detected")
            escalation_score += 30
            print(f"⚠️ WARNING: User {user_id} indicated urgency")
        
        # 5. Check for message repetition (user keeps asking same thing)
        repetition_score = self._check_repetition(user_id, message)
        if repetition_score >= self.REPETITION_THRESHOLD:
            detected_issues.append("message_repetition")
            escalation_score += 50
            print(f"⚠️ WARNING: User {user_id} repeating messages ({repetition_score} times)")
        
        # 6. Check for excessive punctuation (!!!, ???)
        if self._check_excessive_punctuation(message):
            detected_issues.append("excessive_punctuation")
            escalation_score += 20
            print(f"⚠️ WARNING: User {user_id} using excessive punctuation")
        
        # 7. Check for ALL CAPS (shouting)
        if self._check_all_caps(message):
            detected_issues.append("all_caps")
            escalation_score += 25
            print(f"⚠️ WARNING: User {user_id} using ALL CAPS")
        
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
                "timestamp": datetime.datetime.now()
            }
        
        confidence = min(escalation_score / 100, 1.0)
        
        result = {
            "sentiment": sentiment,
            "should_escalate": should_escalate,
            "escalation_reason": escalation_reason,
            "confidence": confidence,
            "escalation_score": escalation_score,
            "detected_issues": detected_issues
        }
        
        print(f"📊 Sentiment Analysis for {user_id}: {result}")
        
        return result
    
    def _check_keywords(self, message: str, keyword_dict: Dict, language: str) -> bool:
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
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, message, re.IGNORECASE):
                return True
        # For offensive: also match elongated variants (5arahhhh, kharaaa, etc.)
        if keyword_dict is self.OFFENSIVE_KEYWORDS:
            message_lower = message.lower()
            for base in ("5ara", "khara", "kol hawa", "kol 5ara", "kol khara"):
                if base in message_lower:
                    # Match base + optional repeated chars (5arahhhh, etc.)
                    flexible = r'\b' + re.escape(base) + r'[a-zA-Z0-9]*\b'
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
        exclamation_count = len(re.findall(r'!{2,}', message))
        question_count = len(re.findall(r'\?{2,}', message))
        
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
    
    def get_escalation_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get escalation information for a user"""
        return self.escalation_reasons.get(user_id)
    
    def clear_user_history(self, user_id: str):
        """Clear history for a user (e.g., after conversation ends)"""
        if user_id in self.user_message_history:
            del self.user_message_history[user_id]
        if user_id in self.escalation_reasons:
            del self.escalation_reasons[user_id]


# Global instance
sentiment_service = SentimentEscalationService()
