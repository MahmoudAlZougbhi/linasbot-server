# services/user_persistence_service.py
"""
User Persistence Service
Ensures gender and language preferences are saved and retrieved from API
Prevents bot from forgetting user preferences
"""

import config
from services.api_integrations import get_customer_by_phone, create_customer, update_customer_gender

class UserPersistenceService:
    """Manages persistent user data (gender, language) via API"""
    
    def __init__(self):
        self._gender_cache = {}  # Cache to avoid repeated API calls
        self._language_cache = {}  # Cache for language preferences
    
    async def get_user_gender(self, user_id: str, phone: str = None) -> str:
        """
        Get user gender from cache or API
        Returns: 'male', 'female', or 'unknown'
        """
        # Check memory first
        if user_id in config.user_gender and config.user_gender[user_id] in ["male", "female"]:
            return config.user_gender[user_id]
        
        # Check cache
        if user_id in self._gender_cache:
            return self._gender_cache[user_id]
        
        # Fetch from API
        try:
            phone_to_check = phone or user_id
            customer_response = await get_customer_by_phone(phone=phone_to_check)
            
            if customer_response and customer_response.get("success"):
                customer_data = customer_response.get("data", {})
                api_gender = customer_data.get("gender", "").lower()
                
                if api_gender in ["male", "female"]:
                    # Update cache and memory
                    self._gender_cache[user_id] = api_gender
                    config.user_gender[user_id] = api_gender
                    print(f"✅ Gender fetched from API for {user_id}: {api_gender}")
                    return api_gender
        except Exception as e:
            print(f"⚠️ Error fetching gender from API for {user_id}: {e}")
        
        return "unknown"
    
    async def save_user_gender(self, user_id: str, gender: str, phone: str = None, name: str = None) -> bool:
        """
        Save user gender to API and cache
        Returns: True if successful, False otherwise
        """
        if gender not in ["male", "female"]:
            print(f"⚠️ Invalid gender value: {gender}")
            return False
        
        try:
            phone_to_use = phone or user_id
            
            # Check if customer exists
            customer_response = await get_customer_by_phone(phone=phone_to_use)
            
            if customer_response and customer_response.get("success") and customer_response.get("data"):
                # Customer exists - update gender
                customer_id = customer_response["data"].get("id")
                if customer_id:
                    update_result = await update_customer_gender(customer_id, gender.capitalize())
                    if update_result and update_result.get("success"):
                        print(f"✅ Gender saved to API for {user_id}: {gender}")
                        # Update cache and memory
                        self._gender_cache[user_id] = gender
                        config.user_gender[user_id] = gender
                        config.gender_attempts[user_id] = 0  # Reset attempts
                        return True
            else:
                # Customer doesn't exist - DON'T create yet
                # Customer will be created when they request an appointment
                print(f"ℹ️ Customer {phone_to_use} not found in API. Gender will be saved when booking appointment.")
                # Just update local cache and memory
                self._gender_cache[user_id] = gender
                config.user_gender[user_id] = gender
                config.gender_attempts[user_id] = 0
                return True  # Return True since we saved locally
        except Exception as e:
            print(f"❌ Error saving gender to API for {user_id}: {e}")
        
        # Even if API fails, save to memory
        config.user_gender[user_id] = gender
        config.gender_attempts[user_id] = 0
        return False
    
    def get_user_language(self, user_id: str) -> str:
        """
        Get user's preferred language from cache
        Returns: 'ar', 'en', 'fr', or 'franco'
        """
        # Check cache first
        if user_id in self._language_cache:
            return self._language_cache[user_id]
        
        # Check config
        user_data = config.user_data_whatsapp.get(user_id, {})
        lang = user_data.get('user_preferred_lang', 'ar')
        
        # Cache it
        self._language_cache[user_id] = lang
        return lang
    
    def save_user_language(self, user_id: str, language: str) -> None:
        """
        Save user's preferred language to cache and config
        Once set, it should not change unless user explicitly switches
        """
        if language not in ['ar', 'en', 'fr', 'franco']:
            print(f"⚠️ Invalid language value: {language}")
            return
        
        # Only update if not already set or if it's the first message
        current_lang = self._language_cache.get(user_id)
        
        if not current_lang:
            # First time setting language - lock it in
            self._language_cache[user_id] = language
            if user_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_id] = {}
            config.user_data_whatsapp[user_id]['user_preferred_lang'] = language
            print(f"🌐 Language locked for {user_id}: {language}")
        else:
            # Language already set - don't change it
            print(f"🔒 Language already locked for {user_id}: {current_lang} (ignoring {language})")
    
    def clear_cache(self, user_id: str = None) -> None:
        """Clear cache for a specific user or all users"""
        if user_id:
            self._gender_cache.pop(user_id, None)
            self._language_cache.pop(user_id, None)
        else:
            self._gender_cache.clear()
            self._language_cache.clear()

# Global instance
user_persistence = UserPersistenceService()
