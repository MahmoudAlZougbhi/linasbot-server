# Gender Detection Service
# Implements requirement #7 from project specifications

from typing import Dict, Optional
import json
import os
from datetime import datetime

class GenderDetectionService:
    """
    Manages gender detection for users
    - Asks new users for gender
    - Checks API for existing users
    - Adapts response style based on gender
    """
    
    def __init__(self):
        # Store gender info temporarily (until API is ready)
        self.user_genders = {}
        self.pending_gender_requests = {}
        
    async def check_user_gender(self, phone: str, api_client=None) -> Optional[str]:
        """
        Check if user gender is known
        Returns: 'male', 'female', or None
        """
        
        # Check local cache first
        if phone in self.user_genders:
            return self.user_genders[phone]
        
        # Try API if available
        if api_client:
            try:
                from services.api_integrations import check_customer_gender
                result = await check_customer_gender(phone=phone)
                if result.get("success") and result.get("data"):
                    gender = result["data"].get("gender", "").lower()
                    if gender in ["male", "female"]:
                        self.user_genders[phone] = gender
                        return gender
            except Exception as e:
                print(f"Error checking gender from API: {e}")
        
        return None
    
    def create_gender_request(self, phone: str, language: str = "ar") -> Dict:
        """Create gender request message for new user"""
        
        self.pending_gender_requests[phone] = {
            "requested_at": datetime.now().isoformat(),
            "language": language
        }
        
        messages = {
            "ar": """👋 أهلاً وسهلاً بك في مركز لينا ليزر!

للمساعدة بشكل أفضل، هل يمكنك إخباري:
هل أنت سيد أم سيدة؟

يرجى الرد بـ:
👨 رجل / ذكر
👩 امرأة / أنثى""",
            
            "en": """👋 Welcome to Lina's Laser Center!

To assist you better, could you please tell me:
Are you male or female?

Please reply with:
👨 Male
👩 Female""",
            
            "fr": """👋 Bienvenue au Centre Laser Lina!

Pour mieux vous aider, pourriez-vous me dire:
Êtes-vous un homme ou une femme?

Veuillez répondre avec:
👨 Homme
👩 Femme"""
        }
        
        return {
            "message": messages.get(language, messages["ar"]),
            "waiting_for_gender": True
        }
    
    def process_gender_response(self, phone: str, message: str) -> Optional[str]:
        """
        Process user's gender response
        Returns detected gender or None
        """
        
        if phone not in self.pending_gender_requests:
            return None
        
        message_lower = message.lower().strip()
        
        # Male indicators
        male_words = [
            "رجل", "ذكر", "سيد", "male", "man", "homme", "masculin",
            "rajul", "zakar", "m", "👨"
        ]
        
        # Female indicators  
        female_words = [
            "امرأة", "أنثى", "سيدة", "بنت", "female", "woman", "lady", "femme", 
            "féminin", "imra'a", "untha", "f", "👩", "girl", "fille"
        ]
        
        # Check for male
        for word in male_words:
            if word in message_lower:
                self.user_genders[phone] = "male"
                del self.pending_gender_requests[phone]
                return "male"
        
        # Check for female
        for word in female_words:
            if word in message_lower:
                self.user_genders[phone] = "female"
                del self.pending_gender_requests[phone]
                return "female"
        
        return None
    
    def adapt_response_style(self, message: str, gender: str, language: str = "ar") -> str:
        """
        Adapt response style based on gender
        Makes subtle adjustments to be more appropriate
        """
        
        if not gender or gender not in ["male", "female"]:
            return message
        
        # For Arabic, adjust pronouns and greetings
        if language == "ar":
            if gender == "female":
                # Female adjustments
                message = message.replace("عزيزي", "عزيزتي")
                message = message.replace("أخي", "أختي")
                message = message.replace("سيدي", "سيدتي")
                # Add feminine emoji touches
                if "👋" not in message:
                    message = message.replace("مرحباً", "مرحباً 🌸")
            else:
                # Male adjustments
                message = message.replace("عزيزتي", "عزيزي")
                message = message.replace("أختي", "أخي")
                message = message.replace("سيدتي", "سيدي")
        
        elif language == "en":
            if gender == "female":
                message = message.replace("Sir", "Ma'am")
                message = message.replace("Mr.", "Ms.")
            else:
                message = message.replace("Ma'am", "Sir")
                message = message.replace("Ms.", "Mr.")
        
        elif language == "fr":
            if gender == "female":
                message = message.replace("Monsieur", "Madame")
                message = message.replace("cher", "chère")
            else:
                message = message.replace("Madame", "Monsieur")
                message = message.replace("chère", "cher")
        
        return message
    
    def get_gender_confirmation_message(self, gender: str, language: str = "ar") -> str:
        """Get confirmation message after gender is detected"""
        
        messages = {
            "ar": {
                "male": "شكراً لك! 👨 سأتواصل معك بالأسلوب المناسب.\n\nكيف يمكنني مساعدتك اليوم؟",
                "female": "شكراً لكِ! 👩 سأتواصل معكِ بالأسلوب المناسب.\n\nكيف يمكنني مساعدتكِ اليوم؟"
            },
            "en": {
                "male": "Thank you, Sir! 👨 I'll address you appropriately.\n\nHow can I help you today?",
                "female": "Thank you, Ma'am! 👩 I'll address you appropriately.\n\nHow can I help you today?"
            },
            "fr": {
                "male": "Merci Monsieur! 👨 Je m'adresserai à vous de manière appropriée.\n\nComment puis-je vous aider aujourd'hui?",
                "female": "Merci Madame! 👩 Je m'adresserai à vous de manière appropriée.\n\nComment puis-je vous aider aujourd'hui?"
            }
        }
        
        return messages.get(language, messages["ar"]).get(gender, "Thank you!")
    
    def is_waiting_for_gender(self, phone: str) -> bool:
        """Check if we're waiting for gender response from user"""
        return phone in self.pending_gender_requests

# Global instance
gender_service = GenderDetectionService()