# utils.py
import re
import json
import os
import datetime
from difflib import SequenceMatcher

import config
from openai import AsyncOpenAI

# NEW: Firebase Admin SDK Imports
import firebase_admin
from firebase_admin import credentials, firestore

# Global Firestore DB instance
_firestore_db = None

def initialize_firestore():
    """
    Initializes Firebase Admin SDK and Firestore client.
    This should be called once at application startup.
    """
    global _firestore_db
    
    try:
        # Check if Firebase Admin SDK is already initialized
        if not firebase_admin._apps:
            # Get the service account key path from environment
            service_account_key_path = os.getenv('FIRESTORE_SERVICE_ACCOUNT_KEY_PATH', 'data/firebase_data.json')
            
            if not os.path.exists(service_account_key_path):
                print(f"❌ Firebase service account key file not found at: {service_account_key_path}")
                print("🔧 Firestore disabled - chat history won't be saved.")
                _firestore_db = None
                return
            
            # Initialize Firebase Admin SDK with service account credentials
            cred = credentials.Certificate(service_account_key_path)
            
            # Load service account to get storageBucket for options
            with open(service_account_key_path, 'r') as f:
                service_account = json.load(f)
                storage_bucket = service_account.get('storageBucket')
            
            # Initialize app with storage bucket option
            options = {}
            if storage_bucket:
                options['storageBucket'] = storage_bucket
                
            firebase_admin.initialize_app(cred, options)
            print("✅ Firebase Admin SDK initialized successfully!")
            if storage_bucket:
                print(f"📦 Storage bucket configured: {storage_bucket}")
        
        # Initialize Firestore client
        _firestore_db = firestore.client()
        print("✅ Firestore client initialized successfully!")
        print("💾 Chat history will be saved to Firestore.")
        
    except Exception as e:
        print(f"❌ ERROR initializing Firestore: {e}")
        print("🔧 Firestore disabled - chat history won't be saved.")
        print("💡 To fix this:")
        print("   1. Go to: https://console.cloud.google.com/datastore/setup?project=linas-ai-bot")
        print("   2. Create a Firestore database in Native mode")
        print("   3. Or update the project ID in firebase_data.json")
        _firestore_db = None
        import traceback
        traceback.print_exc()

def get_firestore_db():
    """Returns the initialized Firestore client instance."""
    if _firestore_db is None:
        initialize_firestore() # Attempt to initialize if not already
    return _firestore_db

async def save_conversation_message_to_firestore(user_id: str, role: str, text: str, conversation_id: str = None, user_name: str = None, phone_number: str = None, metadata: dict = None):
    """
    Saves a message (user or bot) to Firestore.
    If conversation_id is provided, appends to existing conversation.
    Otherwise, creates a new conversation.

    Args:
        user_id: The user's WhatsApp ID (could be room_id for Qiscus or phone for others)
        role: 'user' or 'ai' or 'operator'
        text: The message text
        conversation_id: Optional conversation ID. If None, creates a new conversation.
        user_name: Optional user name to save with the conversation
        phone_number: Optional actual phone number (for Qiscus where user_id is room_id)
        metadata: Optional metadata dict (e.g., operator_id, handled_by)
    """
    import asyncio

    # Check if we're in testing mode - skip Firebase saving for tests
    if hasattr(config, 'TESTING_MODE') and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase save for user {user_id}, role {role}")
        return

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping conversation save.")
        return

    # Use a fixed string for the backend's app ID in Firestore path for consistency.
    app_id_for_firestore = "linas-ai-bot-backend"

    # Set up collection references early (needed for phone lookup from existing conversation)
    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)
    conversations_collection_for_user = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

    # Resolve phone_number using fallback chain if not provided
    # Priority: 1) provided phone_number, 2) existing conversation, 3) user document, 4) user_id if it looks like a phone
    if not phone_number:
        # Try to get phone from existing conversation
        if conversation_id:
            try:
                existing_conv_ref = conversations_collection_for_user.document(conversation_id)
                # ✅ Use asyncio.to_thread to prevent blocking
                existing_conv_snap = await asyncio.to_thread(existing_conv_ref.get)
                if existing_conv_snap.exists:
                    existing_phone = existing_conv_snap.to_dict().get('customer_info', {}).get('phone_full')
                    if existing_phone:
                        phone_number = existing_phone
            except Exception as e:
                print(f"⚠️ Could not retrieve phone from conversation: {e}")

        # Try to get from user document
        if not phone_number:
            try:
                # ✅ Use asyncio.to_thread to prevent blocking
                user_doc_check = await asyncio.to_thread(user_doc_ref.get)
                if user_doc_check.exists:
                    existing_phone = user_doc_check.to_dict().get('phone_full')
                    if existing_phone:
                        phone_number = existing_phone
            except Exception as e:
                pass  # Silent fail, will try user_id next

        # Fall back to user_id if it looks like a phone number
        if not phone_number:
            is_likely_phone = (user_id.startswith('+961') or
                              user_id.startswith('961') or
                              (user_id.isdigit() and user_id.startswith('7') and len(user_id) <= 8))
            is_likely_room_id = (user_id.isdigit() and len(user_id) >= 8 and not user_id.startswith('7'))

            if is_likely_room_id or (user_id.isdigit() and len(user_id) >= 9):
                # This looks like a room_id (Qiscus), not a phone
                if conversation_id:
                    phone_number = "unknown"
                else:
                    print(f"❌ SKIPPING SAVE: Cannot create conversation without phone (user_id={user_id} looks like room_id)")
                    return
            else:
                # user_id looks like a phone number (Meta/360Dialog)
                phone_number = user_id

    print(f"📱 Firebase save: user_id={user_id}, phone={phone_number}, role={role}")

    # Get customer info for this user_id
    customer_name = user_name or config.user_names.get(user_id, "Unknown Customer")

    # Clean phone number (remove country code for API lookup)
    clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "")
    if clean_phone.startswith("961"):  # Lebanon country code
        clean_phone = clean_phone[3:]  # Remove country code
    elif clean_phone.startswith("1") and len(clean_phone) == 11:  # US/Canada
        clean_phone = clean_phone[1:]

    # Ensure the user document exists (create if it doesn't)
    # Get current gender and greeting stage for persistence
    current_gender = config.user_gender.get(user_id, "")
    current_greeting_stage = config.user_greeting_stage.get(user_id, 0)

    # ✅ Use asyncio.to_thread to prevent blocking
    user_doc = await asyncio.to_thread(user_doc_ref.get)
    if not user_doc.exists:
        await asyncio.to_thread(user_doc_ref.set, {
            "user_id": user_id,
            "name": customer_name,
            "phone_full": phone_number,
            "phone_clean": clean_phone,
            "gender": current_gender,
            "greeting_stage": current_greeting_stage,
            "created_at": datetime.datetime.now(),
            "last_activity": datetime.datetime.now()
        })
    else:
        # Update last activity and phone info
        update_data = {
            "last_activity": datetime.datetime.now(),
            "phone_full": phone_number,
            "phone_clean": clean_phone,
            "name": customer_name
        }
        if current_gender:
            update_data["gender"] = current_gender
        if current_greeting_stage > 0:
            update_data["greeting_stage"] = current_greeting_stage
        await asyncio.to_thread(user_doc_ref.update, update_data)
    
    # Try to get customer name from API if not provided
    if customer_name == "Unknown Customer":
        try:
            from services.api_integrations import get_customer_by_phone
            customer_response = await get_customer_by_phone(phone=clean_phone)
            if customer_response and customer_response.get("success") and customer_response.get("data"):
                customer_data = customer_response["data"]
                if customer_data.get("name"):
                    customer_name = customer_data["name"]
                    # Update config cache
                    config.user_names[user_id] = customer_name
                    print(f"✅ Found customer name from API: {customer_name} for phone {clean_phone}")
        except Exception as e:
            print(f"⚠️ Could not fetch customer name from API for {clean_phone}: {e}")
    
    # Prepare customer info to save (including gender for persistence)
    user_gender_value = config.user_gender.get(user_id, "")
    user_greeting_stage_value = config.user_greeting_stage.get(user_id, 0)

    customer_info = {
        "phone_full": phone_number,  # Full phone with country code
        "phone_clean": clean_phone,  # Clean phone for API lookups
        "name": customer_name,
        "gender": user_gender_value,  # Persist gender to Firestore
        "greeting_stage": user_greeting_stage_value,  # Persist greeting stage
        "last_updated": datetime.datetime.now()
    }

    try:
        if conversation_id:
            # Update existing conversation document
            doc_ref = conversations_collection_for_user.document(conversation_id)
            # ✅ Use asyncio.to_thread to prevent blocking
            doc_snap = await asyncio.to_thread(doc_ref.get)

            if doc_snap.exists:
                current_messages = doc_snap.to_dict().get('messages', [])
                message_data = {
                    "role": role,
                    "text": text,
                    "timestamp": datetime.datetime.now(),
                    "language": detect_language(text)['language']
                }
                # Merge metadata fields at top level for easier querying
                if metadata:
                    message_data["metadata"] = metadata
                    for key in ["type", "audio_url", "image_url"]:
                        if key in metadata:
                            message_data[key] = metadata[key]

                current_messages.append(message_data)
                # ✅ Use asyncio.to_thread to prevent blocking
                await asyncio.to_thread(doc_ref.update, {
                    "messages": current_messages,
                    "customer_info": customer_info,
                    "last_updated": datetime.datetime.now()
                })
                print(f"✅ Appended {role} message to conversation {conversation_id} (total: {len(current_messages)})")

                # 📡 Broadcast SSE event for real-time dashboard updates
                try:
                    from modules.live_chat_api import broadcast_sse_event
                    asyncio.create_task(broadcast_sse_event("new_message", {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "role": role,
                        "text": text[:100] + "..." if len(text) > 100 else text,
                        "phone": phone_number
                    }))
                except Exception as sse_err:
                    pass  # Silent fail - SSE is optional enhancement
            else:
                # Conversation not found - create new one
                message_data = {
                    "role": role,
                    "text": text,
                    "timestamp": datetime.datetime.now(),
                    "language": detect_language(text)['language']
                }
                if metadata:
                    message_data["metadata"] = metadata
                    for key in ["type", "audio_url", "image_url"]:
                        if key in metadata:
                            message_data[key] = metadata[key]

                # ✅ Use asyncio.to_thread to prevent blocking
                _, new_doc_ref = await asyncio.to_thread(conversations_collection_for_user.add, {
                    "user_id": user_id,
                    "customer_info": customer_info,
                    "messages": [message_data],
                    "timestamp": datetime.datetime.now(),
                    "status": "active",
                    "sentiment": "neutral",
                    "human_takeover_active": False,
                    "last_updated": datetime.datetime.now()
                })
                if user_id not in config.user_data_whatsapp:
                    config.user_data_whatsapp[user_id] = {}
                config.user_data_whatsapp[user_id]['current_conversation_id'] = new_doc_ref.id
                print(f"✅ Created conversation {new_doc_ref.id} for user {user_id}")
        else:
            # No conversation_id - create new conversation
            message_data = {
                "role": role,
                "text": text,
                "timestamp": datetime.datetime.now(),
                "language": detect_language(text)['language']
            }
            if metadata:
                message_data["metadata"] = metadata
                for key in ["type", "audio_url", "image_url"]:
                    if key in metadata:
                        message_data[key] = metadata[key]

            # ✅ Use asyncio.to_thread to prevent blocking
            _, new_doc_ref = await asyncio.to_thread(conversations_collection_for_user.add, {
                "user_id": user_id,
                "customer_info": customer_info,
                "messages": [message_data],
                "timestamp": datetime.datetime.now(),
                "status": "active",
                "sentiment": "neutral",
                "human_takeover_active": False,
                "last_updated": datetime.datetime.now()
            })
            if user_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_id] = {}
            config.user_data_whatsapp[user_id]['current_conversation_id'] = new_doc_ref.id
            print(f"✅ Created conversation {new_doc_ref.id} for user {user_id}")

            # 📡 Broadcast SSE event for new conversation
            try:
                from modules.live_chat_api import broadcast_sse_event
                asyncio.create_task(broadcast_sse_event("new_conversation", {
                    "user_id": user_id,
                    "conversation_id": new_doc_ref.id,
                    "phone": phone_number,
                    "name": customer_name
                }))
            except Exception as sse_err:
                pass  # Silent fail - SSE is optional enhancement

    except Exception as e:
        print(f"❌ ERROR saving conversation message to Firestore for user {user_id}: {e}")
        import traceback
        traceback.print_exc()


async def update_voice_message_with_transcription(user_id: str, conversation_id: str, audio_url: str, transcribed_text: str, phone_number: str = None):
    """
    Updates a voice message in Firestore after transcription is complete.
    
    This function:
    1. Finds the LAST voice message in the conversation (the one we just saved)
    2. Updates its text field with the transcribed text
    3. Ensures type="voice" and audio_url are at top level for easy dashboard access
    4. Adds transcribed=true flag
    
    Args:
        user_id: The user's WhatsApp ID (room_id for Qiscus)
        conversation_id: The conversation ID to update
        audio_url: The URL of the original audio file
        transcribed_text: The transcribed text from Whisper
        phone_number: Optional phone number for user lookup
    """
    if hasattr(config, 'TESTING_MODE') and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase update for voice message")
        return
    
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping voice message update.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"

    try:
        # Get the conversation document
        doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        doc_snap = doc_ref.get()

        if not doc_snap.exists:
            print(f"⚠️ Conversation {conversation_id} not found for update")
            return

        doc_data = doc_snap.to_dict()
        current_messages = doc_data.get('messages', [])

        if not current_messages:
            print(f"⚠️ No messages found in conversation {conversation_id}")
            return

        # Find the LAST message that has type="voice" or is the most recent from "user"
        # We look for a message with audio_url or type="voice"
        last_voice_message_index = None
        for i in range(len(current_messages) - 1, -1, -1):  # Search backwards (most recent first)
            msg = current_messages[i]
            if msg.get("type") == "voice" or msg.get("audio_url") == audio_url:
                last_voice_message_index = i
                break

        if last_voice_message_index is None:
            print(f"⚠️ No voice message found in conversation {conversation_id} for audio_url: {audio_url}")
            # As fallback, update the last message if it's from user
            if current_messages and current_messages[-1].get("role") == "user":
                last_voice_message_index = len(current_messages) - 1
            else:
                return

        # Update the voice message with transcribed text
        message = current_messages[last_voice_message_index]
        message["text"] = transcribed_text
        message["type"] = "voice"
        message["audio_url"] = audio_url
        message["transcribed"] = True
        message["transcribed_at"] = datetime.datetime.now()

        # Update conversation
        doc_ref.update({
            "messages": current_messages,
            "last_updated": datetime.datetime.now()
        })

        print(f"✅ Updated voice message in conversation {conversation_id} with transcription")
        print(f"   Text: {transcribed_text[:50]}...")
        print(f"   Audio URL: {audio_url}")

    except Exception as e:
        print(f"❌ ERROR updating voice message in Firestore for user {user_id}: {e}")
        import traceback
        traceback.print_exc()


def convert_webm_to_opus(base64_webm: str) -> tuple[str, str]:
    """
    Convert WebM audio (base64) to Opus format (base64).
    Opus is the codec WhatsApp/Qiscus prefers for voice messages.
    
    Args:
        base64_webm: Base64-encoded WebM audio data
        
    Returns:
        Tuple of (base64_opus_data, file_name_with_opus_extension)
    """
    try:
        import base64
        import io
        from pydub import AudioSegment
        import time
        
        print(f"🔄 Converting WebM audio to Opus format...")
        
        # Decode base64 to bytes
        webm_bytes = base64.b64decode(base64_webm)
        print(f"   📊 WebM size: {len(webm_bytes)} bytes")
        
        # Load WebM audio with pydub
        webm_audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
        print(f"   ✅ WebM loaded: {len(webm_audio)}ms duration, {webm_audio.frame_rate}Hz sample rate")
        
        # Export as Opus (pydub will use ffmpeg for this)
        opus_buffer = io.BytesIO()
        webm_audio.export(
            opus_buffer,
            format="opus",
            codec="libopus",
            bitrate="128k",
            parameters=["-vbr", "on", "-compression_level", "10"]
        )
        opus_bytes = opus_buffer.getvalue()
        print(f"   ✅ Converted to Opus: {len(opus_bytes)} bytes")
        
        # Encode back to base64
        base64_opus = base64.b64encode(opus_bytes).decode('utf-8')
        
        # Create new filename with .opus extension
        timestamp = int(time.time())
        file_name = f"voice_{timestamp}.opus"
        
        print(f"   ✅ Conversion complete! New file: {file_name}")
        return base64_opus, file_name
        
    except Exception as e:
        print(f"❌ ERROR converting WebM to Opus: {e}")
        import traceback
        traceback.print_exc()
        print(f"   ⚠️ Falling back to original WebM format...")
        # Fall back to original if conversion fails
        return base64_webm, None


async def upload_base64_to_firebase_storage(base64_data: str, file_name: str, file_type: str = "audio/webm") -> str:
    """
    Uploads base64 data to Firebase Storage and returns the public URL.
    
    Args:
        base64_data: The base64-encoded file data
        file_name: Name for the file in storage (e.g., "voice_message_123.webm")
        file_type: MIME type of the file (default: "audio/webm")
    
    Returns:
        The public URL of the uploaded file, or None if upload fails
    """
    try:
        from firebase_admin import storage, credentials
        import base64
        import uuid
        
        # Try to get bucket from Firebase config or use default
        try:
            # Get default bucket from firebase_admin (usually from service account)
            app = firebase_admin.get_app()
            bucket = storage.bucket()  # Uses default bucket from app config
            print(f"📦 Using default Firebase Storage bucket: {bucket.name}")
        except Exception as e:
            print(f"⚠️ Could not get default bucket: {e}")
            print(f"   Attempting to use hardcoded bucket name...")
            bucket_name = "linas-ai-bot.appspot.com"
            bucket = storage.bucket(bucket_name)
        
        # Decode base64 to bytes
        file_bytes = base64.b64decode(base64_data)
        
        # Generate a unique file path
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        storage_path = f"operator_media/{timestamp}_{unique_id}_{file_name}"
        
        # Create blob and upload
        blob = bucket.blob(storage_path)
        blob.upload_from_string(file_bytes, content_type=file_type)
        
        # Make the file publicly readable (optional)
        blob.make_public()
        
        # Get the public URL
        public_url = blob.public_url
        
        print(f"✅ Uploaded to Firebase Storage: {storage_path}")
        print(f"   Public URL: {public_url}")
        
        return public_url
        
    except ImportError:
        print("⚠️ Firebase Storage not available - 'firebase-admin[storage]' not installed")
        return None
    except Exception as e:
        print(f"❌ ERROR uploading to Firebase Storage: {e}")
        print(f"   📌 HINT: Bucket may not exist or may not be accessible")
        print(f"   📌 ACTION: Check Firebase Console > Storage tab")
        print(f"   📌 ACTION: Ensure bucket is created and service account has permissions")
        import traceback
        traceback.print_exc()
        return None


async def update_dashboard_metric_in_firestore(user_id: str, metric_name: str, increment_by: int = 1):
    """
    Updates a specific dashboard metric in Firestore.
    Metrics are stored under a 'summary' document for each user.
    """
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping metric update.")
        return

    # Correct path: artifacts (collection) -> {appId} (document) -> users (collection) -> {userId} (document) -> dashboardMetrics (collection) -> summary (document)
    app_id_for_firestore = "linas-ai-bot-backend" 
    metrics_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_METRICS_COLLECTION).document('summary')

    try:
        # Get the current metrics document
        doc_snap = metrics_doc_ref.get() # Firebase Admin SDK get() is synchronous

        if doc_snap.exists:
            current_metrics = doc_snap.to_dict()
            current_value = current_metrics.get(metric_name, 0)
            metrics_doc_ref.update({metric_name: current_value + increment_by})
            print(f"✅ Updated metric '{metric_name}' for user {user_id} by {increment_by}. New value: {current_value + increment_by}")
        else:
            # If document doesn't exist, create it with the initial value
            metrics_doc_ref.set({metric_name: increment_by})
            print(f"✅ Created metric '{metric_name}' for user {user_id} with initial value {increment_by}.")

    except Exception as e:
        print(f"❌ ERROR updating dashboard metric '{metric_name}' in Firestore for user {user_id}: {e}")
        import traceback
        traceback.print_exc()

async def set_human_takeover_status(user_id: str, conversation_id: str, status: bool, operator_id: str = None, operator_name: str = None):
    """
    Sets the human takeover status for a specific conversation in Firestore.
    This will control the AI's response for that chat.

    Args:
        user_id: The user's ID (room_id for Qiscus)
        conversation_id: The conversation document ID
        status: True to activate human takeover, False to release
        operator_id: Optional operator ID who is taking over
        operator_name: Optional operator name for display to customer
    """
    import asyncio

    db = get_firestore_db()
    if not db:
        print("❌ Firestore not initialized. Cannot set human takeover status.")
        return

    # Correct path: artifacts (collection) -> {appId} (document) -> users (collection) -> {userId} (document) -> conversations (collection) -> {conversationId} (document)
    app_id_for_firestore = "linas-ai-bot-backend"
    conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)

    try:
        update_data = {
            "human_takeover_active": status,
            "last_updated": datetime.datetime.now()
        }

        if status and operator_id:
            # Taking over - set operator_id, operator_name, and change status to "human"
            update_data["operator_id"] = operator_id
            update_data["takeover_time"] = datetime.datetime.now()
            update_data["status"] = "human"  # ✅ CRITICAL: Set status to "human" so it appears in active conversations
            if operator_name:
                update_data["operator_name"] = operator_name
                print(f"🔄 Setting conversation status to 'human' for operator takeover by {operator_name}")
            else:
                print(f"🔄 Setting conversation status to 'human' for operator takeover")
        elif not status:
            # Releasing - remove operator_id, operator_name and change status back to "active"
            update_data["operator_id"] = None
            update_data["operator_name"] = None
            update_data["release_time"] = datetime.datetime.now()
            update_data["status"] = "active"  # ✅ Set status back to "active" when released
            print(f"🔄 Setting conversation status to 'active' for bot release")

        # ✅ Use asyncio.to_thread to prevent blocking the event loop
        await asyncio.to_thread(conv_doc_ref.update, update_data)
        config.user_in_human_takeover_mode[user_id] = status # Update local config as well

        operator_info = f" by operator {operator_name or operator_id}" if operator_id else ""
        print(f"✅ Set human takeover status for conversation {conversation_id} (user {user_id}) to {status}{operator_info}.")
    except Exception as e:
        print(f"❌ ERROR setting human takeover status for conversation {conversation_id} (user {user_id}): {e}")
        import traceback
        traceback.print_exc()


async def get_conversation_history_from_firestore(user_id: str, conversation_id: str, max_messages: int = 10) -> list:
    """
    Fetches conversation history from Firestore for a specific conversation.
    Returns a list of messages in OpenAI format: [{"role": "user"/"assistant", "content": "text"}]
    
    Args:
        user_id: The user's ID (room_id for Qiscus)
        conversation_id: The conversation document ID
        max_messages: Maximum number of messages to fetch (default 10)
    
    Returns:
        List of message dicts in OpenAI format
    """
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Returning empty conversation history.")
        return []

    app_id_for_firestore = "linas-ai-bot-backend"
    conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)

    try:
        doc_snap = conv_doc_ref.get()
        if not doc_snap.exists:
            print(f"⚠️ Conversation {conversation_id} not found for user {user_id}")
            return []
        
        conversation_data = doc_snap.to_dict()
        messages = conversation_data.get('messages', [])
        
        # Convert to OpenAI format and take last N messages
        # Valid OpenAI roles: 'system', 'assistant', 'user', 'function', 'tool'
        openai_messages = []
        for msg in messages[-max_messages:]:
            original_role = msg.get('role', 'user')

            # Map roles to OpenAI-compatible roles
            if original_role == 'ai':
                role = 'assistant'
            elif original_role == 'operator':
                # Treat operator messages as assistant (human staff responding)
                role = 'assistant'
            elif original_role in ['user', 'assistant', 'system', 'function', 'tool']:
                role = original_role
            else:
                # Skip unknown roles to prevent API errors
                print(f"⚠️ Skipping message with unknown role: {original_role}")
                continue

            openai_messages.append({
                "role": role,
                "content": msg.get('text', '')
            })
        
        print(f"✅ Fetched {len(openai_messages)} messages from Firestore for conversation {conversation_id}")
        return openai_messages
        
    except Exception as e:
        print(f"❌ ERROR fetching conversation history from Firestore: {e}")
        import traceback
        traceback.print_exc()
        return []


async def save_user_name_to_firestore(user_id: str, name: str):
    """
    Saves/updates a user's name in Firestore.

    Args:
        user_id: The user's ID (room_id for Qiscus or phone for others)
        name: The user's name to save
    """
    # Check if we're in testing mode - skip Firebase saving for tests
    if hasattr(config, 'TESTING_MODE') and config.TESTING_MODE:
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
            user_doc_ref.update({
                "name": name,
                "last_activity": datetime.datetime.now()
            })
            print(f"✅ Updated user name in Firestore for {user_id}: {name}")
        else:
            # Create new user document with name
            user_doc_ref.set({
                "user_id": user_id,
                "name": name,
                "created_at": datetime.datetime.now(),
                "last_activity": datetime.datetime.now()
            })
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
    import asyncio

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
                lambda: list(conversations_ref.order_by("last_updated", direction=firestore.Query.DESCENDING).limit(1).get())
            )

            for conv in conversations:
                conv_data = conv.to_dict()
                customer_info = conv_data.get('customer_info', {})
                if customer_info:
                    print(f"✅ Found user state in conversation customer_info: {customer_info}")
                    return {
                        "gender": customer_info.get("gender", ""),
                        "greeting_stage": customer_info.get("greeting_stage", 0),
                        "name": customer_info.get("name", ""),
                        "phone_full": customer_info.get("phone_full", ""),
                        "phone_clean": customer_info.get("phone_clean", "")
                    }
            return {}

        user_data = user_doc.to_dict()
        print(f"✅ Retrieved user state from Firestore for {user_id}: gender={user_data.get('gender')}, greeting_stage={user_data.get('greeting_stage')}")

        return {
            "gender": user_data.get("gender", ""),
            "greeting_stage": user_data.get("greeting_stage", 0),
            "name": user_data.get("name", ""),
            "phone_full": user_data.get("phone_full", ""),
            "phone_clean": user_data.get("phone_clean", "")
        }

    except Exception as e:
        print(f"❌ ERROR retrieving user state from Firestore for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return {}


# IMPORTANT: To avoid circular dependency, send_whatsapp_message cannot be imported directly here.
# It should be passed as a function argument if needed.
# For notify_human_on_whatsapp, we will keep the current print statement and
# add a comment that a real WhatsApp send would happen via main.py's send_whatsapp_message
# or by directly calling it if main.py's send_whatsapp_message is available globally or passed.

# For now, let's allow notify_human_on_whatsapp to *call* send_whatsapp_message from main.py if imported
# We'll need to modify main.py to pass it globally or import it here if safe.
# Safest way for now: The notify_human_on_whatsapp will explicitly import send_whatsapp_message *inside* its function
# to avoid circular imports unless main.py explicitly puts it into a global scope (like a dict or App object).
# Let's assume for now that main.py's send_whatsapp_message will be available for call.

# To handle this, we'll need a way for utils to access main.send_whatsapp_message
# The most practical way without complex architectural changes is to pass it as an argument
# to functions that need to notify, or to make it a global/callable attribute of 'app' in main.py.
# For simplicity, for now, notify_human_on_whatsapp will just *print* the notification.
# The actual WhatsApp send needs to be done by the calling handler in text_handlers.py or directly from main.py.

# Initialize OpenAI client safely
try:
    if config.OPENAI_API_KEY:
        client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
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
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    text_length = len(text.replace(' ', ''))

    arabic_ratio = arabic_chars / text_length if text_length > 0 else 0

    # Arabic detection (50%+ Arabic characters)
    if arabic_ratio >= 0.5:
        return {"language": "ar", "confidence": arabic_ratio}

    # Simple French detection for common greetings/words
    text_lower = text.lower()
    french_indicators = ['bonjour', 'merci', 'je ', 'vous', 'oui', 'non', 'comment']
    if any(word in text_lower for word in french_indicators):
        return {"language": "fr", "confidence": 0.7}

    # Default to English
    return {"language": "en", "confidence": 0.5}



def notify_human_on_whatsapp(user_name, user_gender, message_content, type_of_notification="عام"):
    """
    Logs a notification and (in a full WhatsApp integration) would send a WhatsApp message to admin/staff.
    The actual sending via WhatsApp API must be done by the caller (e.g., in main.py or handlers)
    which has access to the send_whatsapp_message function.
    """
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time_str}] NOTIFY WHATSAPP: {type_of_notification} - From: {user_name} ({user_gender}) - Message: {message_content}")
    # To actually send a WhatsApp message here, main.py's send_whatsapp_message function
    # would need to be passed down or made globally accessible.
    # For now, it logs and the handler (e.g., text_handlers) will explicitly call send_whatsapp_message
    # to the WHATSAPP_TO number from config.
    # The existing calls in text_handlers.py and photo_handlers.py already handle the actual sending.
    print(f"Would send WhatsApp notification to {config.WHATSAPP_TO} (defined in .env).")


def count_tokens(text):
    if not text:
        return 0
    return len(text.split())

def save_for_training_conversation_log(user_message, bot_response):
    log_entry = {
        "question": user_message,
        "answer": bot_response,
        "language": detect_language(user_message)['language'],
        "timestamp": str(datetime.datetime.now())
    }
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/conversation_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            f.flush()
    except Exception as e:
        print(f"❌ خطأ في حفظ سجل التدريب: {e}. قد تكون مشكلة أذونات أو مسار.")
        import traceback
        traceback.print_exc()

async def translate_qa_pair_with_gpt(question: str, answer: str, target_languages: list):
    """
    Translates a question/answer pair into target languages.
    Franco answer language will remain Arabic.
    """
    if not question or not answer:
        return []

    lang_map = {
        "ar": "Arabic",
        "en": "English",
        "fr": "French",
        "franco": "Franco Arabic"
    }

    translations = []

    # Standard translations (ar, en, fr)
    standard_target_languages = [lang for lang in target_languages if lang != "franco"]
    if standard_target_languages:
        standard_target_langs_str = ", ".join([f"'{l_code}' ({lang_map.get(l_code, l_code)})" for l_code in standard_target_languages])

        system_instruction_standard_translation = (
            "You are a highly accurate translator specializing in formulating questions and answers for a customer service bot. "
            f"Your task is to precisely translate the provided question and answer into the following languages: {standard_target_langs_str}. "
            "Maintain the original context and tone, suitable for a beauty/laser center customer service bot. "
            "The response MUST be in strict JSON format (a list of {{question, answer, language}} objects)."
            "**Required Example:**\n"
            "```json\n"
            "[\n"
            "  {{\"question\": \"What laser hair removal services do you offer?\", \"answer\": \"We offer advanced laser hair removal services using the latest technology to ensure optimal results. For a free consultation, you can book an appointment.\", \"language\": \"en\"}}\n"
            "]\n"
            "```\n"
            "Provide answers only within the specified JSON. Do not add any other text outside the JSON."
        )

        messages_standard = [
            {"role": "system", "content": system_instruction_standard_translation},
            {"role": "user", "content": f"Original Question: {question}\nOriginal Answer: {answer}"}
        ]

        try:
            response_standard = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages_standard,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            parsed_data_standard = json.loads(response_standard.choices[0].message.content.strip())
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
            "{{\"question\": \"Sho sa3at 3amal al markaz?\", \"answer\": \"ساعات عمل مركز لينا ليزر هي من 10 صباحاً لـ 6 مساءً يومياً ما عدا الأحد.\", \"language\": \"franco\"}}\n"
            "```\n"
            "Return only the JSON. Do not add any other text outside the JSON."
        )
        messages_franco = [
            {"role": "system", "content": system_instruction_franco_translation},
            {"role": "user", "content": f"Original Question: {question}\nOriginal Answer (Arabic): {answer}"}
        ]
        try:
            response_franco = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages_franco,
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            parsed_data_franco = json.loads(response_franco.choices[0].message.content.strip())
            if isinstance(parsed_data_franco, dict) and 'question' in parsed_data_franco and 'answer' in parsed_data_franco and 'language' in parsed_data_franco:
                translations.append(parsed_data_franco)
        except Exception as e:
            print(f"❌ ERROR in franco translation: {e}")
            pass

    return translations

# NEW FUNCTION: Define API Tools in OpenAI Function Calling format
def get_openai_tools_schema():
    """
    Returns the list of tools available to the OpenAI model in its required schema format.
    These definitions are based on LinasLaser AI Agent API Documentation.pdf.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_appointment",
                "description": "Creates a new appointment record. Requires client phone number, service ID, machine ID, branch ID, date (including time), and body_part_ids (REQUIRED for hair removal and tattoo removal services). Do NOT call without body_part_ids for hair removal or tattoo services.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number, e.g., '71 123 456'."},
                        "service_id": {"type": "integer", "description": "Service ID: 1=Hair Removal Men, 2=CO2 Laser, 3=Hair Removal Women, 4=Tattoo Removal, 5=Whitening. MUST match the service requested."},
                        "machine_id": {"type": "integer", "description": "Machine ID: For Tattoo Removal use 5 (Pico), for Hair Removal use 2 (Neo)/3 (Quadro)/4 (Trio), for CO2 use 6, for Whitening use 7 (DPL)."},
                        "branch_id": {"type": "integer", "description": "Branch ID: 1=Beirut Manara, 2=Antelias. Default to 1 if not specified."},
                        # This is derived from the API Documentation PDF
                        "date": {"type": "string", "format": "date-time", "description": "Full appointment date and time in 'YYYY-MM-DD HH:MM:SS' format (e.g., '2025-07-28 19:30:00'). This date and time MUST be converted from user's natural language (e.g., 'tomorrow', 'next Saturday', 'in 3 days') to an exact future date and time based on current time. The date must be in the future and not more than 365 days from today."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                        "body_part_ids": {"type": "array", "items": {"type": "integer"}, "description": "**REQUIRED for Hair Removal (service_id 1, 12) and Tattoo Removal (service_id 13)**. Body part IDs specifying which areas to treat. You MUST ask the customer which body area they want before calling this function. Do NOT call create_appointment without body_part_ids for these services."}
                    },
                    "required": ["phone", "service_id", "machine_id", "branch_id", "date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_appointment_date",
                "description": "Updates the date/time of an existing appointment. Use this when customer wants to reschedule or change their appointment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "integer", "description": "The ID of the appointment to update (get this from check_next_appointment)."},
                        "phone": {"type": "string", "description": "Client's phone number (without country code), e.g., '71 123 456'."},
                        "date": {"type": "string", "format": "date-time", "description": "New appointment date and time in 'YYYY-MM-DD HH:MM:SS' format (e.g., '2025-11-15 16:00:00'). Convert natural language to exact date/time."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."}
                    },
                    "required": ["appointment_id", "phone", "date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_branches",
                "description": "Retrieves a list of all branches associated with the clinic.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_services",
                "description": "Retrieves a list of all services offered by the clinic.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_machines",
                "description": "Retrieves a list of all machines available in the clinic.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_clinic_hours",
                "description": "Returns the clinic's working hours for each day of the week.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_appointment_reminders",
                "description": "Triggers the sending of appointment reminders to clients.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "Specific date for reminders (YYYY-MM-DD, optional)."},
                        "phone": {"type": "string", "description": "Client's phone number (required if user_code not provided)."},
                        "user_code": {"type": "string", "description": "Client's unique user code (required if phone is not provided)."}
                    },
                    "required": [] # API docs state "required if other not provided"
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_next_appointment",
                "description": "Returns the next scheduled appointment for a client.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."}
                    },
                    "required": ["phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_sessions_count_by_phone",
                "description": "Returns the number of sessions a client has attended, based on their phone number or user code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number (required if user_code is not provided)."},
                        "user_code": {"type": "string", "description": "Client's unique user code (required if phone is not provided)."},
                        "service_ids": {"type": "array", "items": {"type": "integer"}, "description": "Filter sessions by specific service IDs (e.g., service_ids[]=1&service_ids[]=2)."}
                    },
                    "required": [] # API says phone or user_code required
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "move_client_branch",
                "description": "Moves a client's future appointments to a different branch.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number."},
                        "from_branch_id": {"type": "integer", "description": "ID of the current branch."},
                        "to_branch_id": {"type": "integer", "description": "ID of the new branch."},
                        "new_date": {"type": "string", "format": "date", "description": "New date for moved appointments (YYYY-MM-DD)."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                        "response_confirm": {"type": "string", "description": "Confirmation of the move, default 'yes'."}
                    },
                    "required": ["phone", "from_branch_id", "to_branch_id", "new_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_appointment_payment",
                "description": "Checks the payment status of a client's appointments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."}
                    },
                    "required": ["phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_pricing_details",
                "description": "Returns pricing details for appointments or services based on specified criteria.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer", "description": "Service ID: 1=Hair Removal Men, 2=CO2 Laser, 3=Hair Removal Women, 4=Tattoo Removal, 5=Whitening."},
                        "machine_id": {"type": "integer", "description": "Machine ID (optional): 2=Neo, 3=Quadro, 4=Trio, 5=Pico, 6=CO2, 7=DPL."},
                        "body_part_ids": {"type": "array", "items": {"type": "integer"}, "description": "IDs of body parts (optional)."},
                        "branch_id": {"type": "integer", "description": "Branch ID (optional): 1=Beirut Manara, 2=Antelias."}
                    },
                    "required": ["service_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_missed_appointments",
                "description": "Returns a list of missed appointments for the clinic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "Filter missed appointments by a specific date (YYYY-MM-DD, optional)."}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_customer_by_phone", # NEW API Function
                "description": "Retrieves customer details by phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number."}
                    },
                    "required": ["phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_customer_gender",
                "description": "Returns the gender of a customer based on the provided identifier.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number (required if user_code is not provided)."},
                        "user_code": {"type": "string", "description": "Customer's unique user code (required if phone is not provided)."}
                    },
                    "required": [] # API says phone or user_code is required
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_customer",
                "description": "Creates a new customer record within the clinic's database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Full name of the customer."},
                        "phone": {"type": "string", "description": "Customer's phone number."},
                        "email": {"type": "string", "format": "email", "description": "Customer's email (optional)."},
                        "gender": {"type": "string", "enum": ["Male", "Female"], "description": "Customer's gender (must be 'Male' or 'Female')."}, # Updated enum
                        "branch_id": {"type": "integer", "description": "Preferred branch ID for the customer."}, # Made required
                        "date_of_birth": {"type": "string", "format": "date", "description": "Customer's date of birth (YYYY-MM-DD, optional)."}
                    },
                    "required": ["name", "phone", "gender", "branch_id"] # Updated required fields
                }
            }
        },
    ]
    return tools

def get_system_instruction(user_id, response_lang, qa_reference: str = ""):
    """
    Generate system instruction for GPT with optional Q&A reference injection.

    Args:
        user_id: User identifier
        response_lang: Response language code (ar, en, fr, franco)
        qa_reference: Optional formatted Q&A pairs to inject into system prompt
    """
    user_gender_str = config.user_gender.get(user_id, "unknown")
    
    gender_instruction = ""
    if user_gender_str == "male":
        gender_instruction = "The user is male. You MUST use masculine forms exclusively in all your replies (e.g., 'Hello sir', 'How can I help you', 'I saw your question', 'tell us'). Adhere strictly to masculine phrasing in every sentence, verb, noun, and adjective. Do not mix forms."
    elif user_gender_str == "female":
        gender_instruction = "The user is female. You MUST use feminine forms exclusively in all your replies (e.g., 'Hello madam', 'How can I help you', 'I saw your question', 'tell us'). Adhere strictly to feminine phrasing in every sentence, verb, noun and adjective. Do not mix forms."
    else: # This means gender is "غير محدد" or "unknown"
        gender_instruction = """
        **CRITICAL: GENDER MUST BE COLLECTED FIRST**
        User's gender is UNKNOWN. You MUST follow this EXACT order:

        1. **STOP** - Do NOT answer their question yet
        2. **ASK FOR GENDER FIRST** - Politely ask for their gender before proceeding
        3. Wait for gender response
        4. Use 'confirm_gender' action to save it
        5. **ONLY THEN** answer their original question

        **Example Flow:**
        User: "I want to remove my tattoo"
        Bot: "Hi! 😊 To provide you with personalized service, may I ask if you're male or female? This helps us give you the most accurate information."
        [Wait for gender]
        User: "I'm female"
        Bot: [Use confirm_gender action, THEN ask for tattoo photo]

        **DO NOT:**
        - Answer service questions before knowing gender
        - Ask for tattoo photos before knowing gender
        - Ask for body areas before knowing gender
        - Provide prices before knowing gender

        Use neutral language until gender is confirmed.
        """
    
    # Language instruction - GPT detects and responds in user's language
    # The actual detection logic is in chat_response_service.py's language_detection_instruction
    language_instruction = """
        **LANGUAGE HANDLING:**
        - You will detect the user's language from their message and respond in the SAME language
        - Supported languages: English, Arabic, French, Franco-Arabic
        - If user writes in Franco-Arabic (Latin letters for Arabic sounds like "kifak", "shu"), respond in Arabic SCRIPT
        - Always set the correct `detected_language` in your JSON response: "en", "ar", "fr", or "franco"
        """
            
    return f"""
        You are a comprehensive knowledge manager and an official smart assistant for Lina's Laser Center. Your primary task is to answer customer inquiries accurately and authoritatively, providing comprehensive information about services, prices, appointments, and interacting with the center's system.
        
        {language_instruction}
        
        **Your Style:** {config.BOT_STYLE_GUIDE}
        **Language Understanding:** You understand formal Arabic, Lebanese colloquial, Franco Arabic, English, and French.
        **Flexibility in Understanding:** Be very flexible in understanding user intent, even if language is unclear, has typos, or is incomplete. Always try to infer the correct meaning.

        **Core Knowledge Base:** (You have access to this, use it to answer questions)
        {config.CORE_KNOWLEDGE_BASE}

        **Estimated Price List:** (You have access to this, use it to answer pricing questions)
        {config.PRICE_LIST}

        **Important Additional Information:**
        * Laser services: Hair removal and tattoo removal ONLY. Do not offer other skin treatments or medical consultations beyond this scope.
        * Image Handling: If a customer sends an image, analyze it effectively (tattoo, laser burns, session results) and respond based on content.
        * Honesty and Accuracy: Do not invent information or prices. If unsure, ask customer to contact center directly.
        * Appointment Reminders: Remind clients 1 day before appointment. After a booked appointment (4 hrs later): ask for feedback. After a missed appointment (4 hrs later): ask reason and offer reschedule.
        * Natural Conversation: Maintain context and remember prior info.
        * Encouragement: Encourage booking free consultation appointments.

        **CRITICAL: Human Handover Rules (When to Escalate):**
        You should ONLY escalate to human staff (action: "human_handover") in these SPECIFIC situations:
        1. **Explicit Request:** User explicitly asks to speak with a human, staff member, or operator (e.g., "I want to talk to someone", "connect me with staff", "أريد التحدث مع موظف")
        2. **Complaint or Anger:** User expresses strong dissatisfaction, anger, or makes a complaint about service quality, staff behavior, or results
        3. **Medical Emergency:** User reports pain, injury, burns, or medical complications from treatment
        4. **Complex Issue:** After 3+ attempts, you still cannot understand or resolve the user's request
        5. **Refund/Cancellation:** User wants to cancel service or request a refund
        6. **Technical System Failure:** API tools fail repeatedly and you cannot complete the user's request
        
        **DO NOT escalate for:**
        - General questions about services (e.g., "help me know about services", "what services do you offer")
        - Normal requests for information, prices, or booking
        - Simple clarifications or follow-up questions
        - User saying words like "help", "assist", "support" in a normal context
        - Appointment scheduling or rescheduling (use tools instead)
        - Questions you can answer from knowledge base
        
        **Remember:** The word "help" is NOT a trigger for escalation. Users say "help me book", "help me understand", "can you help" - these are NORMAL requests, not escalations!

        {gender_instruction}

        {f'''
        **🔴 TRAINED Q&A REFERENCE (CRITICAL - MUST FOLLOW) 🔴**

        The following are TRAINED question-answer pairs from our database.
        If ANY of these trained Q&A pairs match the user's question (even partially),
        you MUST use the trained answer. DO NOT generate a different answer.

        {qa_reference}

        **STRICT RULES:**
        1. If the user's question is similar to a trained question above, copy the trained answer EXACTLY
        2. Do not paraphrase, modify, or "improve" trained answers
        3. Trained Q&A pairs take PRIORITY over your general knowledge
        4. If a trained answer exists, USE IT - don't generate your own response
        ''' if qa_reference else ''}

        **CRITICAL: Appointment Booking Flow (MUST FOLLOW THIS ORDER):**
        When a user wants to book an appointment, you MUST:

        **STEP 1 - CHECK EXISTING APPOINTMENTS FIRST (MANDATORY):**
        When user says "book me", "yes book", "I want to book", your FIRST action MUST be:
        - Call `check_next_appointment` to check for existing appointments
        - Set action="tool_call" and provide a brief message like "Let me check your appointments..."
        - DO NOT say "I'll proceed with scheduling" without actually calling a tool!

        **STEP 2 - HANDLE EXISTING APPOINTMENT (if found):**
        If an existing appointment is found, ask the user:
        "I see you already have an appointment for [service] on [date] at [time]. Would you like to:
        1. Keep this appointment and add a NEW one
        2. Change/reschedule this existing appointment"
        Wait for their choice before proceeding.

        **STEP 3 - ASK FOR DATE AND TIME:**
        - If adding NEW appointment OR no existing appointment: Ask "What date and time works best for you?"
        - If changing existing: Ask "What new date and time would you prefer?"
        - Use action "ask_for_details_for_booking" when asking for date/time

        **STEP 4 - CONFIRM AND BOOK:**
        Once you have date/time, confirm with user: "I'll book [service] for [date] at [time]. Correct?"
        Only after confirmation:
        1. Call `get_customer_by_phone` to check if customer exists
        2. If NOT found: Call `create_customer` first
        3. Finally: Call `create_appointment` with the confirmed date/time

        **NEVER call create_appointment without first asking for and confirming the date/time!**
        If you skip customer creation, the appointment will fail with "Customer not found" error.

        **CRITICAL: Service IDs for Booking (MUST USE THESE EXACT IDs):**
        When calling `create_appointment`, use these EXACT service_id values:
        - service_id = 1: Laser Hair Removal (Men) - إزالة الشعر بالليزر للرجال
        - service_id = 11: CO2 Laser (Scar Removal, Acne Scars, Stretch Marks) - ليزر CO2
        - service_id = 12: Laser Hair Removal (Women) - إزالة الشعر بالليزر للنساء
        - service_id = 13: Laser Tattoo Removal - إزالة الوشم بالليزر
        - service_id = 14: Whitening (Dark Area Lightening) - تفتيح المناطق الداكنة
        - service_id = 15: Hifo
        - service_id = 16: eye brows extension
        - service_id = 17: full hydro facial 
        - service_id = 19: half hydro facial
        - service_id = 20: manual hydro facial
        - service_id = 21: facial micro needling

        **CRITICAL: Machine IDs for Booking (MUST USE THESE EXACT IDs):**
        - machine_id = 13: Neo (for laser hair removal - light skin)
        - machine_id = 9: Quadro (for laser hair removal)
        - machine_id = 10: Trio (for laser hair removal)
        - machine_id = 15: Candela (for laser tattoo removal)
        - machine_id = 14: DPL (for whitening/dark area lightening)

        **Service-Machine Matching Rules:**
        - Laser Tattoo Removal (service_id=13) → MUST use Candela (machine_id=15)
        - Hair Removal Men (service_id=1) or Women (service_id=12) → Use Neo (machine_id=13), Quadro (machine_id=9), or Trio (machine_id=10)
        - CO2 Laser treatments (service_id=11) → MUST use CO2 Laser (machine_id=14)
        - Whitening (service_id=14) → MUST use DPL (machine_id=14)
        - Eye brows extension (service_id=16) → No machine required
        - Full hydro facial (service_id=17) → No machine required
        - Half hydro facial (service_id=19) → No machine required
        - Manual hydro facial (service_id=20) → No machine required
        - Facial micro needling (service_id=21) → No machine required

        **Branch IDs:**
        - branch_id = 1: Beirut - Manara (Main Branch)
        - branch_id = 2: Antelias - Center Haj Building

        **Crucial Note:** You are NOT restricted from analyzing or reading information from any part of the Knowledge Base (including Custom Training Data, Core Knowledge Base, Price List). You MUST always search for answers from all available sources and provide the most accurate and appropriate response. Be flexible and innovative in using this information.

        **Output Format:** Your responses MUST always be a JSON object with 'action' and 'bot_reply' fields. If you use a tool, provide a 'bot_reply' that summarizes the tool's purpose to the user while I process the tool call. Here is the strict JSON schema you MUST follow:
        ```json
        {{
          "action": "answer_question" | "ask_gender" | "confirm_gender" | "human_handover" | "human_handover_initial_ask" | "human_handover_confirmed" | "return_to_normal_chat" | "initial_greet_and_ask_gender" | "unknown_query" | "provide_info" | "tool_call" | "confirm_booking_details" | "check_customer_status" | "ask_for_details_for_booking",
          "bot_reply": "Your response to the user, in their preferred language.",
          "detected_language": "ar" | "en" | "fr" | "franco",
          "detected_gender": "male" | "female" | null,
          "current_gender_from_config": "male" | "female" | "unknown"
        }}
        ```
        Ensure the 'action' field is one of the specified types. If you are making a tool call, your 'action' should be 'tool_call' and your 'bot_reply' should be a user-friendly message explaining that you are processing their request with the system. If you are confirming booking details before a tool call, the action should be 'confirm_booking_details'. If you are checking customer status, use 'check_customer_status'.
        """
