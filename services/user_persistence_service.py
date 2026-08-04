"""
User Persistence Service
Ensures gender and language preferences are saved and retrieved from Firestore
Prevents bot from forgetting user preferences
"""

from __future__ import annotations

import asyncio
import datetime
import re
from typing import cast

import config
from services.api_integrations import get_customer_by_phone
from utils.phone_utils import normalize_phone
from utils.utils import get_firestore_db, get_user_state_from_firestore


class UserPersistenceService:
    """Manages persistent user data (gender, language) via Firestore"""

    def __init__(self) -> None:
        self._gender_cache: dict[str, str] = {}  # Cache to avoid repeated Firestore calls
        self._language_cache: dict[str, str] = {}  # Cache for language preferences

    async def get_user_gender(self, user_id: str, phone: str | None = None) -> str:
        """
        Get user gender from cache, Firestore, or API
        Returns: 'male', 'female', or 'unknown'
        """
        # Check memory first
        if user_id in config.user_gender and config.user_gender[user_id] in ["male", "female"]:
            return config.user_gender[user_id]

        # Check cache
        if user_id in self._gender_cache:
            return cast(str, self._gender_cache[user_id])

        # Fetch from Firestore first (primary source)
        try:
            user_state = await get_user_state_from_firestore(user_id)
            if user_state and user_state.get("gender") in ["male", "female"]:
                firestore_gender = user_state["gender"]
                self._gender_cache[user_id] = firestore_gender
                config.user_gender[user_id] = firestore_gender
                print(f"✅ Gender fetched from Firestore for {user_id}: {firestore_gender}")
                return cast(str, firestore_gender)
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
                    return cast(str, api_gender)
        except Exception as e:
            print(f"⚠️ Error fetching gender from API for {user_id}: {e}")

        return "unknown"

    async def save_user_gender(
        self, user_id: str, gender: str, phone: str | None = None, name: str | None = None
    ) -> bool:
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
                user_doc_ref = (
                    db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)
                )

                # ✅ Use asyncio.to_thread to prevent blocking the event loop
                user_doc = await asyncio.to_thread(user_doc_ref.get)
                if user_doc.exists:
                    # Update existing document - include greeting_stage for persistence
                    await asyncio.to_thread(
                        user_doc_ref.update,
                        {
                            "gender": gender,
                            "greeting_stage": 2,  # Skip gender question on restore
                            "last_updated": datetime.datetime.now(),
                        },
                    )
                else:
                    # Create new user document
                    await asyncio.to_thread(
                        user_doc_ref.set,
                        {
                            "user_id": user_id,
                            "gender": gender,
                            "greeting_stage": 2,  # Skip gender question on restore
                            "phone_full": phone or user_id,
                            "name": name or config.user_names.get(user_id, "Unknown"),
                            "created_at": datetime.datetime.now(),
                            "last_updated": datetime.datetime.now(),
                        },
                    )

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
                conversations_ref = (
                    db.collection("artifacts")
                    .document(app_id_for_firestore)
                    .collection("users")
                    .document(user_id)
                    .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                )

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

                    await asyncio.to_thread(
                        conv_ref.update, {"customer_info": customer_info, "last_updated": datetime.datetime.now()}
                    )
                    print(f"✅ Gender updated in conversation {conv.id} customer_info for {user_id}")
                    break
        except Exception as e:
            print(f"⚠️ Error updating conversation customer_info with gender for {user_id}: {e}")
            import traceback

            traceback.print_exc()

        return firestore_saved or True  # Return True if at least memory was updated

    async def save_social_booking_preference(
        self,
        user_id: str,
        preference_key: str,
        preference: str,
    ) -> bool:
        """Persist one scoped social booking preference in the existing user document.

        The opaque key is a SHA-256 scope fingerprint supplied by the social router.
        This deliberately does not use or alter the legacy/global ``gender`` field.
        """
        if preference not in {"male", "female"}:
            raise ValueError("Invalid social booking preference")
        if not re.fullmatch(r"[0-9a-f]{64}", preference_key):
            raise ValueError("Invalid social booking preference key")

        db = get_firestore_db()
        if not db:
            print("[social-preference] persistence_unavailable")
            return False

        from services.social_contact_routing import SOCIAL_BOOKING_PREFERENCES_FIELD

        app_id_for_firestore = "linas-ai-bot-backend"
        user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)
        record = {
            "value": preference,
            "updated_at": datetime.datetime.now(),
        }
        try:
            user_doc = await asyncio.to_thread(user_doc_ref.get)
            if user_doc.exists:
                await asyncio.to_thread(
                    user_doc_ref.update,
                    {
                        f"{SOCIAL_BOOKING_PREFERENCES_FIELD}.{preference_key}": record,
                        "last_updated": datetime.datetime.now(),
                    },
                )
            else:
                await asyncio.to_thread(
                    user_doc_ref.set,
                    {
                        "user_id": user_id,
                        SOCIAL_BOOKING_PREFERENCES_FIELD: {preference_key: record},
                        "created_at": datetime.datetime.now(),
                        "last_updated": datetime.datetime.now(),
                    },
                )
        except Exception as exc:
            # Provider errors can contain customer identifiers; retain only the type.
            print(f"[social-preference] persistence_failed type={type(exc).__name__}")
            return False

        print("[social-preference] persistence_saved")
        return True

    def get_user_language(self, user_id: str) -> str:
        """
        Get user's preferred language from cache
        Returns: 'ar', 'en', 'fr', or 'franco'
        """
        # Check cache first
        if user_id in self._language_cache:
            return cast(str, self._language_cache[user_id])

        # Check config
        user_data = config.user_data_whatsapp.get(user_id, {})
        lang = user_data.get("user_preferred_lang", "ar")

        # Cache it
        self._language_cache[user_id] = lang
        return cast(str, lang)

    def _phone_language_lookup_keys(self, raw_phone: str) -> list[str]:
        """Candidate WhatsApp user_id keys used in config.user_data_whatsapp / cache."""
        p = (raw_phone or "").strip()
        if not p:
            return []
        keys = [p]
        e164 = normalize_phone(p)
        if e164:
            keys.append(e164)
            keys.append(e164.lstrip("+"))
        digits = "".join(c for c in p if c.isdigit())
        if digits and digits not in keys:
            keys.append(digits)
        seen = set()
        out = []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def resolve_language_for_phone(self, raw_phone: str) -> tuple[str, str]:
        """
        Find saved preferred language for a phone number (same keys the bot uses).
        Returns (language, source) where source is 'saved' or 'default'.
        """
        for uid in self._phone_language_lookup_keys(raw_phone):
            if uid in self._language_cache:
                return self._language_cache[uid], "saved"
            user_data = config.user_data_whatsapp.get(uid, {})
            lang = user_data.get("user_preferred_lang")
            if lang:
                return lang, "saved"
        return "ar", "default"

    @staticmethod
    def normalize_template_language_code(lang: str | None) -> str:
        """Map persisted / detected codes to smart_messaging template keys (ar, en, fr)."""
        s = (lang or "ar").strip().lower()
        if s == "franco":
            return "ar"
        if s in ("en", "fr", "ar"):
            return s
        return "ar"

    async def _language_from_firestore_latest_conversation(self, user_id: str) -> str | None:
        """Read language from the most recently updated conversation doc for this user."""
        if not user_id:
            return None
        db = get_firestore_db()
        if not db:
            return None
        from google.cloud import firestore

        app_id = "linas-ai-bot-backend"
        conv_col = (
            db.collection("artifacts")
            .document(app_id)
            .collection("users")
            .document(user_id)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
        )
        try:
            docs = await asyncio.to_thread(
                lambda: list(conv_col.order_by("last_updated", direction=firestore.Query.DESCENDING).limit(5).get())
            )
        except Exception as e:
            print(f"⚠️ language lookup order_by failed for {user_id}: {e}")
            docs = await asyncio.to_thread(lambda: list(conv_col.limit(40).stream()))

        for doc in docs:
            data = doc.to_dict() or {}
            lang = data.get("language") or (data.get("customer_info") or {}).get("language")
            if lang and str(lang).strip():
                return str(lang).strip()
        return None

    async def enrich_language_from_firestore_if_needed(
        self,
        raw_phone: str,
        extra_firestore_user_ids: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Resolve (language, source) with in-memory preference first, then Firestore conversation docs.
        source is 'saved' or 'default'.
        """
        lang, src = self.resolve_language_for_phone(raw_phone)
        if src == "saved" and lang:
            return self.normalize_template_language_code(lang), "saved"

        candidates: list[str] = []
        for x in extra_firestore_user_ids or []:
            xs = str(x).strip() if x else ""
            if xs and xs not in candidates:
                candidates.append(xs)
        for k in self._phone_language_lookup_keys(raw_phone):
            if k and k not in candidates:
                candidates.append(k)

        seen = set()
        for uid in candidates:
            if not uid or uid in seen:
                continue
            seen.add(uid)
            lang_fs = await self._language_from_firestore_latest_conversation(uid)
            if lang_fs:
                return self.normalize_template_language_code(lang_fs), "saved"

        return self.normalize_template_language_code(lang), "default"

    async def resolve_language_for_campaign_recipient(
        self,
        raw_phone: str,
        *,
        firestore_user_id: str | None = None,
        fallback_language: str = "ar",
    ) -> str:
        """Language for manual campaign text; uses fallback_language when nothing is stored."""
        extra = [firestore_user_id] if firestore_user_id else None
        lang, src = await self.enrich_language_from_firestore_if_needed(raw_phone, extra)
        if src == "default":
            return self.normalize_template_language_code(fallback_language)
        return lang

    def save_user_language(self, user_id: str, language: str) -> None:
        """
        Save user's preferred language to cache and config
        Language can change on each message based on detection
        """
        if language not in ["ar", "en", "fr", "franco"]:
            print(f"⚠️ Invalid language value: {language}")
            return

        # Always update language - users can switch languages mid-conversation
        previous_lang = self._language_cache.get(user_id)
        self._language_cache[user_id] = language

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {}
        config.user_data_whatsapp[user_id]["user_preferred_lang"] = language

        if previous_lang and previous_lang != language:
            print(f"🌐 Language updated for {user_id}: {previous_lang} → {language}")
        else:
            print(f"🌐 Language set for {user_id}: {language}")

    def clear_cache(self, user_id: str | None = None) -> None:
        """Clear cache for a specific user or all users"""
        if user_id:
            self._gender_cache.pop(user_id, None)
            self._language_cache.pop(user_id, None)
        else:
            self._gender_cache.clear()
            self._language_cache.clear()


# Global instance
user_persistence = UserPersistenceService()
