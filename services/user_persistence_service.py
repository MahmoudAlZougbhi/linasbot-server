# services/user_persistence_service.py
"""
User Persistence Service
Ensures gender and language preferences are saved and retrieved from Firestore
Prevents bot from forgetting user preferences
"""

import config
import datetime
from services.api_integrations import get_customer_by_phone, create_customer
from utils.utils import get_user_state_from_firestore, get_firestore_db

class UserPersistenceService:
    """Manages persistent user data (gender, language) via Firestore"""

    def __init__(self):
        self._gender_cache = {}  # Cache to avoid repeated Firestore calls
        self._language_cache = {}  # Cache for language preferences

    async def get_user_gender(self, user_id: str, phone: str = None) -> str:
        """
        Get user gender from cache, Firestore, or API
        Returns: 'male', 'female', or 'unknown'
        """
        # Check memory first
        if user_id in config.user_gender and config.user_gender[user_id] in ["male", "female"]:
            return config.user_gender[user_id]

        # Check cache
        if user_id in self._gender_cache:
            return self._gender_cache[user_id]

        # Fetch from Firestore first (primary source)
        try:
            user_state = await get_user_state_from_firestore(user_id)
            if user_state and user_state.get("gender") in ["male", "female"]:
                firestore_gender = user_state["gender"]
                self._gender_cache[user_id] = firestore_gender
                config.user_gender[user_id] = firestore_gender
                print(f"✅ Gender fetched from Firestore for {user_id}: {firestore_gender}")
                return firestore_gender
        except Exception as e:
            print(f"⚠️ Error fetching gender from Firestore for {user_id}: {e}")

        # Fallback: Fetch from external API
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
        Save user gender to Firestore and cache
        Returns: True if successful, False otherwise
        """
        import asyncio

        if gender not in ["male", "female"]:
            print(f"⚠️ Invalid gender value: {gender}")
            return False

        # Update local cache and memory FIRST (always works)
        self._gender_cache[user_id] = gender
        config.user_gender[user_id] = gender
        config.gender_attempts[user_id] = 0  # Reset attempts

        # CRITICAL: Also set greeting_stage to 2 so we skip the gender question on restore
        config.user_greeting_stage[user_id] = 2

        # Save to Firestore (primary persistence)
        firestore_saved = False
        try:
            db = get_firestore_db()
            if db:
                app_id_for_firestore = "linas-ai-bot-backend"
                user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)

                # ✅ Use asyncio.to_thread to prevent blocking the event loop
                user_doc = await asyncio.to_thread(user_doc_ref.get)
                if user_doc.exists:
                    # Update existing document - include greeting_stage for persistence
                    await asyncio.to_thread(user_doc_ref.update, {
                        "gender": gender,
                        "greeting_stage": 2,  # Skip gender question on restore
                        "last_updated": datetime.datetime.now()
                    })
                else:
                    # Create new user document
                    await asyncio.to_thread(user_doc_ref.set, {
                        "user_id": user_id,
                        "gender": gender,
                        "greeting_stage": 2,  # Skip gender question on restore
                        "phone_full": phone or user_id,
                        "name": name or config.user_names.get(user_id, "Unknown"),
                        "created_at": datetime.datetime.now(),
                        "last_updated": datetime.datetime.now()
                    })

                firestore_saved = True
                print(f"✅ Gender saved to Firestore for {user_id}: {gender}")
        except Exception as e:
            print(f"⚠️ Error saving gender to Firestore for {user_id}: {e}")
            import traceback
            traceback.print_exc()

        # Also update the most recent conversation's customer_info (for dashboard visibility)
        try:
            db = get_firestore_db()
            if db:
                app_id_for_firestore = "linas-ai-bot-backend"
                conversations_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

                # Get the most recent conversation - use asyncio.to_thread
                from google.cloud.firestore import Query
                recent_convs = await asyncio.to_thread(
                    lambda: list(conversations_ref.order_by("last_updated", direction=Query.DESCENDING).limit(1).get())
                )

                for conv in recent_convs:
                    conv_ref = conversations_ref.document(conv.id)
                    conv_data = conv.to_dict()
                    customer_info = conv_data.get("customer_info", {})
                    customer_info["gender"] = gender
                    customer_info["greeting_stage"] = 2  # Persist greeting_stage for restore

                    await asyncio.to_thread(conv_ref.update, {
                        "customer_info": customer_info,
                        "last_updated": datetime.datetime.now()
                    })
                    print(f"✅ Gender updated in conversation {conv.id} customer_info for {user_id}")
                    break
        except Exception as e:
            print(f"⚠️ Error updating conversation customer_info with gender for {user_id}: {e}")
            import traceback
            traceback.print_exc()

        return firestore_saved or True  # Return True if at least memory was updated
    
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
