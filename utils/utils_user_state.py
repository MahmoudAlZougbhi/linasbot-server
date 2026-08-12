"""User name and persisted user-state Firestore helpers."""

from __future__ import annotations

import asyncio
import datetime
import logging

from firebase_admin import firestore

import config
from utils.utils_firestore import get_firestore_db

_log = logging.getLogger(__name__)


async def save_user_name_to_firestore(user_id: str, name: str) -> None:
    """
    Saves/updates a user's name in Firestore.

    Args:
        user_id: The user's ID (room_id for Qiscus or phone for others)
        name: The user's name to save
    """
    # Check if we're in testing mode - skip Firebase saving for tests
    if hasattr(config, "TESTING_MODE") and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase name save for user {user_id}")
        return

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping user name save.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"
    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)

    try:
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            # Update existing user document with name
            user_doc_ref.update({"name": name, "last_activity": datetime.datetime.now()})
            print(f"✅ Updated user name in Firestore for {user_id}: {name}")
        else:
            # Create new user document with name
            user_doc_ref.set(
                {
                    "user_id": user_id,
                    "name": name,
                    "created_at": datetime.datetime.now(),
                    "last_activity": datetime.datetime.now(),
                }
            )
            print(f"✅ Created user document in Firestore for {user_id} with name: {name}")
    except Exception as e:
        print(f"❌ ERROR saving user name to Firestore for {user_id}: {e}")
        import traceback

        traceback.print_exc()

async def get_user_state_from_firestore(user_id: str) -> dict:
    """
    Retrieves user state (gender, greeting_stage, name, phone) from Firestore.
    This is used to restore user state after server restart.

    Args:
        user_id: The user's ID (room_id for Qiscus)

    Returns:
        Dict with user state: {gender, greeting_stage, name, phone_full, phone_clean}
        Returns empty dict if user not found or error occurs.
    """

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Cannot retrieve user state.")
        return {}

    app_id_for_firestore = "linas-ai-bot-backend"
    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)

    try:
        # ✅ Use asyncio.to_thread to prevent blocking the event loop
        user_doc = await asyncio.to_thread(user_doc_ref.get)
        if not user_doc.exists:
            print(f"ℹ️ No user document found in Firestore for user_id: {user_id}")
            # Try to get from most recent conversation's customer_info
            conversations_ref = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            # ✅ Use asyncio.to_thread for the query
            conversations = await asyncio.to_thread(
                lambda: list(
                    conversations_ref.order_by("last_updated", direction=firestore.Query.DESCENDING).limit(1).get()
                )
            )

            for conv in conversations:
                conv_data = conv.to_dict()
                customer_info = conv_data.get("customer_info", {})
                if customer_info:
                    print(f"✅ Found user state in conversation customer_info: {customer_info}")
                    return {
                        "gender": customer_info.get("gender", ""),
                        "greeting_stage": customer_info.get("greeting_stage", 0),
                        "name": customer_info.get("name", ""),
                        "phone_full": customer_info.get("phone_full", ""),
                        "phone_clean": customer_info.get("phone_clean", ""),
                        "social_booking_preferences": {},
                    }
            return {}

        user_data = user_doc.to_dict()
        print(
            f"✅ Retrieved user state from Firestore for {user_id}: gender={user_data.get('gender')}, greeting_stage={user_data.get('greeting_stage')}"
        )

        social_booking_preferences = user_data.get("social_booking_preferences")
        return {
            "gender": user_data.get("gender", ""),
            "greeting_stage": user_data.get("greeting_stage", 0),
            "name": user_data.get("name", ""),
            "phone_full": user_data.get("phone_full", ""),
            "phone_clean": user_data.get("phone_clean", ""),
            "social_booking_preferences": (
                social_booking_preferences if isinstance(social_booking_preferences, dict) else {}
            ),
        }

    except Exception as e:
        print(f"❌ ERROR retrieving user state from Firestore for {user_id}: {e}")
        import traceback

        traceback.print_exc()
        return {}
