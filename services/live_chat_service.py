# -*- coding: utf-8 -*-
"""
Live Chat Service - Hybrid Approach
- 6-hour time filter for active conversations
- Groups conversations by client (one card per client)
- Status management: active, resolved, archived
- Auto-reopen on new message
"""

import datetime
import asyncio
from typing import List, Dict, Optional, Any
from collections import defaultdict
import config
from utils.utils import get_firestore_db, set_human_takeover_status


class LiveChatService:
    """Service for managing live chat operations with hybrid approach"""

    # Time window for active conversations (7 days in seconds)
    ACTIVE_TIME_WINDOW = 7 * 24 * 60 * 60  # 7 days (changed from 6 hours to prevent auto-archiving)

    # Cache configuration
    CACHE_TTL = 120  # seconds - cache results to avoid repeated slow Firestore queries

    def __init__(self):
        self.operator_sessions = {}
        self.operator_status = defaultdict(lambda: "available")
        # Cache for active conversations
        self._conversations_cache = None
        self._conversations_cache_time = None
        # Cache for waiting queue
        self._queue_cache = None
        self._queue_cache_time = None
        
    async def get_active_conversations(self) -> List[Dict[str, Any]]:
        """
        Get active conversations grouped by client
        - Only shows conversations from last 6 hours
        - Groups multiple conversations per client
        - Excludes resolved/archived conversations
        - Returns one entry per client with their latest conversation
        """
        # Check cache first
        current_time = datetime.datetime.now()
        if (self._conversations_cache is not None and
            self._conversations_cache_time is not None and
            (current_time - self._conversations_cache_time).total_seconds() < self.CACHE_TTL):
            print(f"📦 Returning cached active conversations ({len(self._conversations_cache)} clients)")
            return self._conversations_cache

        try:
            db = get_firestore_db()
            if not db:
                return []
            
            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            
            # Dictionary to group conversations by client
            client_conversations = {}
            current_time = datetime.datetime.now()

            # Limit to 50 users max for performance
            users_docs = list(users_collection.limit(50).stream())

            # Helper function to fetch conversations for a single user
            async def fetch_user_conversations(user_id):
                """Fetch all conversations for a user"""
                try:
                    conversations_collection = users_collection.document(user_id).collection(
                        config.FIRESTORE_CONVERSATIONS_COLLECTION
                    )
                    conversations_docs = list(conversations_collection.stream())
                    return (user_id, conversations_docs)
                except Exception as e:
                    print(f"⚠️ Error fetching conversations for user {user_id}: {e}")
                    return (user_id, [])

            # Fetch conversations for all users in parallel
            user_ids = [doc.id for doc in users_docs]
            conversation_results = await asyncio.gather(
                *[fetch_user_conversations(uid) for uid in user_ids],
                return_exceptions=True
            )

            # Process results
            for result in conversation_results:
                if isinstance(result, Exception):
                    print(f"⚠️ Error in parallel fetch: {result}")
                    continue

                user_id, conversations_docs = result

                # Collect all conversations for this client
                client_convs = []

                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = conv_data.get("messages", [])

                    if not messages:
                        continue

                    # Get conversation status
                    conv_status = conv_data.get("status", "active")

                    # Skip resolved or archived conversations
                    if conv_status in ["resolved", "archived"]:
                        continue

                    # Get last message time
                    last_message = messages[-1]
                    last_message_time = self._parse_timestamp(last_message.get("timestamp"))

                    # Apply time filter
                    time_diff = (current_time - last_message_time).total_seconds()
                    if time_diff > self.ACTIVE_TIME_WINDOW:
                        # Auto-archive old conversations
                        await self._auto_archive_conversation(user_id, conv_doc.id)
                        continue
                    
                    # Get conversation metadata
                    human_takeover = conv_data.get("human_takeover_active", False)
                    operator_id = conv_data.get("operator_id")
                    sentiment = conv_data.get("sentiment", "neutral")
                    
                    # Determine status
                    if human_takeover:
                        status = "human" if operator_id else "waiting_human"
                    else:
                        status = "bot"
                    
                    # Skip conversations waiting for human - they should only appear in waiting queue
                    if status == "waiting_human":
                        continue
                    
                    # Calculate duration
                    first_message_time = self._parse_timestamp(messages[0].get("timestamp"))
                    duration_seconds = int((last_message_time - first_message_time).total_seconds())
                    
                    conversation = {
                        "conversation_id": conv_doc.id,
                        "user_id": user_id,
                        "status": status,
                        "message_count": len(messages),
                        "last_activity": last_message_time.isoformat(),
                        "last_activity_dt": last_message_time,
                        "duration_seconds": duration_seconds,
                        "sentiment": sentiment,
                        "operator_id": operator_id,
                        "last_message": {
                            "content": last_message.get("text", ""),
                            "is_user": last_message.get("role") == "user",
                            "timestamp": last_message_time.isoformat()
                        }
                    }
                    
                    client_convs.append(conversation)
                
                # If client has conversations, group them
                if client_convs:
                    # Sort by last activity (most recent first)
                    client_convs.sort(key=lambda x: x["last_activity_dt"], reverse=True)
                    
                    # Get latest conversation
                    latest_conv = client_convs[0]
                    
                    # Get user info from Firebase customer_info first, fallback to config
                    customer_info = conv_data.get("customer_info", {})
                    user_name = customer_info.get("name") or config.user_names.get(user_id, "Unknown Customer")
                    
                    # CRITICAL: Get phone from customer_info or user_data, NEVER from user_id (which is room_id for Qiscus)
                    phone_full = customer_info.get("phone_full") or config.user_data_whatsapp.get(user_id, {}).get('phone_number') or "Unknown"
                    phone_clean = customer_info.get("phone_clean") or (config.user_data_whatsapp.get(user_id, {}).get('phone_number', '').replace('+', '').replace('-', '').replace(' ', '')) or "Unknown"
                    
                    language = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')
                    
                    # Create grouped client entry
                    client_entry = {
                        "user_id": user_id,
                        "user_name": user_name,
                        "user_phone": phone_full,
                        "phone_clean": phone_clean,
                        "language": language,
                        "conversation_count": len(client_convs),
                        "conversations": client_convs,
                        # Latest conversation details
                        "conversation_id": latest_conv["conversation_id"],
                        "status": latest_conv["status"],
                        "message_count": sum(c["message_count"] for c in client_convs),
                        "last_activity": latest_conv["last_activity"],
                        "duration_seconds": latest_conv["duration_seconds"],
                        "sentiment": latest_conv["sentiment"],
                        "operator_id": latest_conv["operator_id"],
                        "last_message": latest_conv["last_message"]
                    }
                    
                    client_conversations[user_id] = client_entry
            
            # Convert to list and sort by last activity
            active_conversations = list(client_conversations.values())
            active_conversations.sort(key=lambda x: x["last_activity"], reverse=True)

            print(f"📊 Active conversations: {len(active_conversations)} clients (6-hour window)")

            # Update cache
            self._conversations_cache = active_conversations
            self._conversations_cache_time = current_time

            return active_conversations
            
        except Exception as e:
            print(f"❌ Error getting active conversations: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def get_client_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all conversations for a specific client (for expanded view)
        """
        try:
            db = get_firestore_db()
            if not db:
                return []
            
            app_id = "linas-ai-bot-backend"
            conversations_collection = db.collection("artifacts").document(app_id).collection(
                "users"
            ).document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            
            conversations_docs = list(conversations_collection.stream())
            conversations = []
            
            for conv_doc in conversations_docs:
                conv_data = conv_doc.to_dict()
                messages = conv_data.get("messages", [])
                
                if not messages:
                    continue
                
                last_message = messages[-1]
                last_message_time = self._parse_timestamp(last_message.get("timestamp"))
                
                conversations.append({
                    "conversation_id": conv_doc.id,
                    "message_count": len(messages),
                    "last_activity": last_message_time.isoformat(),
                    "status": conv_data.get("status", "active"),
                    "sentiment": conv_data.get("sentiment", "neutral"),
                    "human_takeover_active": conv_data.get("human_takeover_active", False),
                    "operator_id": conv_data.get("operator_id")
                })
            
            conversations.sort(key=lambda x: x["last_activity"], reverse=True)
            return conversations
            
        except Exception as e:
            print(f"❌ Error getting client conversations: {e}")
            return []
    
    async def get_waiting_queue(self) -> List[Dict[str, Any]]:
        """
        Get conversations waiting for human intervention
        Queries Firebase directly for conversations with human_takeover_active=True and operator_id=None
        """
        try:
            db = get_firestore_db()
            if not db:
                return []
            
            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            
            waiting_queue = []
            current_time = datetime.datetime.now()
            
            users_docs = list(users_collection.stream())
            
            for user_doc in users_docs:
                user_id = user_doc.id
                
                conversations_collection = users_collection.document(user_id).collection(
                    config.FIRESTORE_CONVERSATIONS_COLLECTION
                )
                conversations_docs = list(conversations_collection.stream())
                
                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = conv_data.get("messages", [])
                    
                    if not messages:
                        continue
                    
                    # Check if conversation is waiting for human
                    human_takeover = conv_data.get("human_takeover_active", False)
                    operator_id = conv_data.get("operator_id")
                    conv_status = conv_data.get("status", "active")
                    
                    # Only include conversations waiting for human (takeover active but no operator assigned)
                    if not (human_takeover and operator_id is None):
                        continue
                    
                    # Skip resolved/archived
                    if conv_status in ["resolved", "archived"]:
                        continue
                    
                    # Get last message time
                    last_message = messages[-1]
                    last_message_time = self._parse_timestamp(last_message.get("timestamp"))
                    
                    # Apply 6-hour filter
                    time_diff = (current_time - last_message_time).total_seconds()
                    if time_diff > self.ACTIVE_TIME_WINDOW:
                        continue
                    
                    # Calculate wait time
                    escalation_time = conv_data.get("escalation_time")
                    if escalation_time:
                        escalation_dt = self._parse_timestamp(escalation_time)
                        wait_time_seconds = int((current_time - escalation_dt).total_seconds())
                    else:
                        wait_time_seconds = int((current_time - last_message_time).total_seconds())
                    
                    # Get user info from Firebase customer_info first, fallback to config
                    customer_info = conv_data.get("customer_info", {})
                    user_name = customer_info.get("name") or config.user_names.get(user_id, "Unknown Customer")
                    
                    # CRITICAL: Get phone from customer_info or user_data, NEVER from user_id (which is room_id for Qiscus)
                    phone_full = customer_info.get("phone_full") or config.user_data_whatsapp.get(user_id, {}).get('phone_number') or "Unknown"
                    phone_clean = customer_info.get("phone_clean") or (config.user_data_whatsapp.get(user_id, {}).get('phone_number', '').replace('+', '').replace('-', '').replace(' ', '')) or "Unknown"
                    
                    language = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')
                    sentiment = conv_data.get("sentiment", "neutral")
                    
                    # Determine reason and priority
                    escalation_reason = conv_data.get("escalation_reason", "user_request")
                    priority = 1 if sentiment == "negative" or wait_time_seconds > 300 else 2
                    
                    queue_item = {
                        "conversation_id": conv_doc.id,
                        "user_id": user_id,
                        "user_name": user_name,
                        "user_phone": phone_full,
                        "phone_clean": phone_clean,
                        "language": language,
                        "reason": escalation_reason,
                        "wait_time_seconds": wait_time_seconds,
                        "sentiment": sentiment,
                        "message_count": len(messages),
                        "priority": priority,
                        "last_message": last_message.get("text", "")
                    }
                    
                    waiting_queue.append(queue_item)
            
            # Sort by priority (1=high, 2=normal) then by wait time (longest first)
            waiting_queue.sort(key=lambda x: (x["priority"], -x["wait_time_seconds"]))
            
            print(f"📊 Waiting queue: {len(waiting_queue)} conversations")
            
            return waiting_queue
            
        except Exception as e:
            print(f"❌ Error getting waiting queue: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def end_conversation(self, conversation_id: str, user_id: str, operator_id: str, adapter=None) -> Dict[str, Any]:
        """
        Mark conversation as resolved/ended
        - Sets status to 'resolved'
        - Records who resolved it and when
        - Removes from active view
        - Sends notification to customer
        - Can be reopened if customer messages again
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # Update conversation status
            update_data = {
                "status": "resolved",
                "resolved_at": datetime.datetime.now(),
                "resolved_by": operator_id,
                "human_takeover_active": False,
                "operator_id": None
            }
            
            print(f"🔄 Updating conversation {conversation_id} with data: {update_data}")
            conv_ref.update(update_data)
            print(f"✅ Firebase updated successfully for conversation {conversation_id}")
            
            # Verify the update
            updated_doc = conv_ref.get()
            if updated_doc.exists:
                updated_data = updated_doc.to_dict()
                print(f"✅ Verified: status = {updated_data.get('status')}, resolved_by = {updated_data.get('resolved_by')}")
            
            # Update in-memory state
            config.user_in_human_takeover_mode[user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Invalidate cache
            self._conversations_cache = None
            self._queue_cache = None

            # Send notification to customer
            if adapter:
                try:
                    # Multilingual end conversation messages
                    end_messages = {
                        "ar": "شكراً لتواصلك معنا! تم إنهاء المحادثة. إذا كان لديك أي استفسار آخر، لا تتردد في مراسلتنا مجدداً. 🌟",
                        "en": "Thank you for contacting us! This conversation has been ended. If you have any other questions, feel free to message us again. 🌟",
                        "fr": "Merci de nous avoir contactés! Cette conversation est terminée. Si vous avez d'autres questions, n'hésitez pas à nous écrire à nouveau. 🌟"
                    }
                    
                    # Get user's preferred language from config
                    user_lang = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')
                    notification_message = end_messages.get(user_lang, end_messages['ar'])
                    
                    # Send notification via WhatsApp
                    await adapter.send_text_message(user_id, notification_message)
                    print(f"✅ Sent end conversation notification to customer {user_id}")
                    
                    # Save notification to Firebase
                    from utils.utils import save_conversation_message_to_firestore
                    await save_conversation_message_to_firestore(
                        user_id=user_id,
                        role="ai",
                        text=notification_message,
                        conversation_id=conversation_id,
                        metadata={"type": "end_conversation_notification", "operator_id": operator_id}
                    )
                except Exception as e:
                    print(f"⚠️ Failed to send end conversation notification: {e}")
            
            print(f"✅ Conversation {conversation_id} marked as resolved by {operator_id}")
            
            return {
                "success": True,
                "message": "Conversation ended successfully",
                "conversation_id": conversation_id,
                "status": "resolved"
            }
            
        except Exception as e:
            print(f"❌ Error ending conversation: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def reopen_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """
        Reopen a resolved conversation (auto-called when customer messages again)
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # Reopen conversation
            conv_ref.update({
                "status": "active",
                "reopened_at": datetime.datetime.now(),
                "resolved_at": None,
                "resolved_by": None
            })
            
            print(f"✅ Conversation {conversation_id} reopened (customer messaged again)")
            
            return {
                "success": True,
                "message": "Conversation reopened",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"❌ Error reopening conversation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _auto_archive_conversation(self, user_id: str, conversation_id: str):
        """
        Auto-archive conversations older than 6 hours
        """
        try:
            db = get_firestore_db()
            if not db:
                return
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            conv_ref.update({
                "status": "archived",
                "archived_at": datetime.datetime.now(),
                "archived_reason": "auto_6h_timeout"
            })
            
            print(f"📦 Auto-archived conversation {conversation_id} (6-hour timeout)")
            
        except Exception as e:
            print(f"⚠️ Error auto-archiving conversation: {e}")
    
    async def takeover_conversation(self, conversation_id: str, user_id: str, operator_id: str, operator_name: str = None) -> Dict[str, Any]:
        """Operator takes over a conversation"""
        try:
            await set_human_takeover_status(user_id, conversation_id, True, operator_id, operator_name)
            config.user_in_human_takeover_mode[user_id] = True
            self.operator_sessions[conversation_id] = operator_id

            # Invalidate cache
            self._conversations_cache = None
            self._queue_cache = None

            print(f"✅ Operator {operator_id} took over conversation {conversation_id}")

            return {
                "success": True,
                "message": "Conversation taken over successfully",
                "conversation_id": conversation_id,
                "operator_id": operator_id
            }
            
        except Exception as e:
            print(f"❌ Error taking over conversation: {e}")
            return {"success": False, "error": str(e)}
    
    async def release_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """Release conversation back to bot"""
        try:
            await set_human_takeover_status(user_id, conversation_id, False)
            config.user_in_human_takeover_mode[user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Invalidate cache
            self._conversations_cache = None
            self._queue_cache = None

            print(f"✅ Conversation {conversation_id} released back to bot")

            return {
                "success": True,
                "message": "Conversation released to bot successfully",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"❌ Error releasing conversation: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_operator_message(
        self, conversation_id: str, user_id: str, message: str, operator_id: str, adapter, message_type: str = "text"
    ) -> Dict[str, Any]:
        """Send message from operator to customer
        
        Args:
            conversation_id: The conversation ID
            user_id: The customer's user ID (room_id for Qiscus)
            message: Message content (text for text, base64 for voice/image)
            operator_id: The operator's ID
            adapter: WhatsApp adapter instance
            message_type: Type of message - "text", "voice", or "image"
        """
        try:
            from utils.utils import save_conversation_message_to_firestore, get_firestore_db
            
            # For Qiscus, we need to fetch the phone_number from Firebase
            phone_number = None
            db = get_firestore_db()
            if db:
                try:
                    app_id = "linas-ai-bot-backend"
                    user_doc = db.collection("artifacts").document(app_id).collection("users").document(user_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        phone_number = user_data.get("phone_full")
                        print(f"📱 Found phone_number from Firebase: {phone_number}")
                except Exception as e:
                    print(f"⚠️ Could not fetch phone_number from Firebase: {e}")
            
            # Handle different message types
            if message_type == "voice":
                # message contains base64 audio data
                
                print(f"🎙️ Operator {operator_id} recorded voice message for {user_id}")
                
                # Step 0: Convert WebM to Opus (Qiscus/WhatsApp standard)
                print(f"� Converting voice to Opus format (WhatsApp standard)...")
                audio_data_to_upload = message
                upload_file_name = f"voice_{user_id}_{int(__import__('time').time())}.webm"
                upload_file_type = "audio/webm"
                
                try:
                    from utils.utils import convert_webm_to_opus
                    opus_data, opus_file_name = convert_webm_to_opus(message)
                    if opus_file_name:  # Conversion successful
                        audio_data_to_upload = opus_data
                        upload_file_name = opus_file_name
                        upload_file_type = "audio/opus"
                        print(f"✅ Voice converted to Opus")
                except Exception as e:
                    print(f"⚠️ WebM to Opus conversion failed: {e}")
                    print(f"   Continuing with original WebM format...")
                
                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage
                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=audio_data_to_upload,
                        file_name=upload_file_name,
                        file_type=upload_file_type
                    )
                    print(f"✅ Voice uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    if "404" in str(e) and "bucket does not exist" in str(e).lower():
                        print(f"   📌 HINT: Check storageBucket in data/firebase_data.json")
                        print(f"   📌 Actual bucket: linas-ai-bot.firebasestorage.app (not appspot.com)")
                    storage_url = None
                
                # Step 2: Save to Firebase Firestore
                print(f"📝 Saving voice metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=user_id,
                    role="operator",
                    text="[Voice Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "voice",
                        "audio_data": audio_data_to_upload,  # Store converted Opus or fallback WebM
                        "audio_url": storage_url,  # Store the public URL with key name 'audio_url' for easy retrieval
                        "message_length": len(message)
                    }
                )
                
                # Step 3: Send voice message via Qiscus
                print(f"🎙️ Sending voice message via Qiscus to {user_id}...")
                try:
                    if storage_url:
                        # Send as native audio message (plays directly on phone, not just a link)
                        await adapter.send_audio_message(user_id, storage_url)
                        print(f"✅ Sent voice as native audio message via Qiscus")
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام رسالة صوتية من المشغل. يرجى فتح لوحة المعلومات لسماعها."
                        await adapter.send_text_message(user_id, text_notification)
                        print(f"✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via Qiscus: {e}")
                    import traceback
                    traceback.print_exc()
                
                print(f"✅ Voice message processed and sent for {user_id}")
                
                return {"success": True, "message": "Voice message sent successfully", "storage_url": storage_url}
                    
            elif message_type == "image":
                # message contains base64 image data
                print(f"🖼️ Operator {operator_id} uploaded image for {user_id}")
                print(f"📝 Uploading image to Firebase Storage...")
                
                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage
                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=message,
                        file_name=f"image_{user_id}_{int(__import__('time').time())}.jpg",
                        file_type="image/jpeg"
                    )
                    print(f"✅ Image uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    storage_url = None
                
                # Step 2: Save to Firebase Firestore
                print(f"📝 Saving image metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=user_id,
                    role="operator",
                    text="[Image Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "image",
                        "image_data": message,  # Store full base64 as backup
                        "image_url": storage_url,  # Store the public URL with key name 'image_url' for easy retrieval
                        "message_length": len(message)
                    }
                )
                
                # Step 3: Send image via Qiscus
                print(f"🖼️ Sending image via Qiscus to {user_id}...")
                try:
                    if storage_url:
                        # Send as native image message (displays in gallery on phone, not just a link)
                        await adapter.send_image_message(user_id, storage_url, caption="صورة من المشغل")
                        print(f"✅ Sent image as native image message via Qiscus")
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام صورة من المشغل. يرجى فتح لوحة المعلومات لعرضها."
                        await adapter.send_text_message(user_id, text_notification)
                        print(f"✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via Qiscus: {e}")
                    import traceback
                    traceback.print_exc()
                
                print(f"✅ Image message processed and sent for {user_id}")
                
                return {"success": True, "message": "Image message sent successfully", "storage_url": storage_url}
                    
            else:  # Default to text
                # Always save to Firestore first (for live chat history)
                await save_conversation_message_to_firestore(
                    user_id=user_id,
                    role="operator",
                    text=message,
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={"operator_id": operator_id, "handled_by": "human"}
                )
                print(f"✅ Saved operator message to Firestore")

                # Try to send via WhatsApp adapter
                try:
                    result = await adapter.send_text_message(user_id, message)

                    if result.get("success"):
                        print(f"✅ Operator {operator_id} sent message to {user_id} via WhatsApp")
                        return {"success": True, "message": "Message sent successfully"}
                    else:
                        print(f"⚠️ WhatsApp send failed but message saved: {result.get('error')}")
                        return {"success": True, "message": "Message saved (WhatsApp send failed)", "warning": result.get('error')}
                except Exception as send_error:
                    print(f"⚠️ WhatsApp adapter error but message saved: {send_error}")
                    return {"success": True, "message": "Message saved (WhatsApp unavailable)", "warning": str(send_error)}
            
        except Exception as e:
            print(f"❌ Error sending operator message: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def update_operator_status(self, operator_id: str, status: str) -> Dict[str, Any]:
        """Update operator availability"""
        try:
            valid_statuses = ["available", "busy", "away"]
            if status not in valid_statuses:
                return {"success": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}
            
            self.operator_status[operator_id] = status
            print(f"✅ Operator {operator_id} status: {status}")
            
            return {"success": True, "operator_id": operator_id, "status": status}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_conversation_details(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        """Get detailed conversation history"""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            conv_doc = conv_ref.get()
            if not conv_doc.exists:
                return {"success": False, "error": "Conversation not found"}
            
            conv_data = conv_doc.to_dict()
            messages = conv_data.get("messages", [])
            
            formatted_messages = []
            # DEBUG: Count messages by role
            role_counts = {}
            for msg in messages:
                role = msg.get("role", "unknown")
                role_counts[role] = role_counts.get(role, 0) + 1
            print(f"\n🔍 RETRIEVED MESSAGES ROLE DISTRIBUTION:")
            print(f"   Total messages: {len(messages)}")
            for role, count in role_counts.items():
                print(f"   - {role}: {count}")
            print()

            for i, msg in enumerate(messages):
                # Debug: Print first message to see structure
                if i == 0:
                    print(f"🔍 DEBUG first message keys: {list(msg.keys())}")
                    print(f"🔍 DEBUG first message role: '{msg.get('role')}'")
                    print(f"🔍 DEBUG first message text: '{msg.get('text', '')[:50]}'")

                msg_data = {
                    "timestamp": self._parse_timestamp(msg.get("timestamp")).isoformat(),
                    "is_user": msg.get("role") == "user",
                    "content": msg.get("text", ""),
                    "type": msg.get("type", "text"),
                    "handled_by": msg.get("metadata", {}).get("handled_by", "bot"),
                    "role": msg.get("role")  # Debug: Include raw role
                }

                # Add audio_url if it exists (for voice messages) - check both top level and metadata
                audio_url = msg.get("audio_url") or msg.get("metadata", {}).get("audio_url")
                if audio_url:
                    msg_data["audio_url"] = audio_url

                # Add image_url if it exists (for image messages) - check both top level and metadata
                image_url = msg.get("image_url") or msg.get("metadata", {}).get("image_url")
                if image_url:
                    msg_data["image_url"] = image_url

                formatted_messages.append(msg_data)
            
            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": formatted_messages,
                "sentiment": conv_data.get("sentiment", "neutral"),
                "status": conv_data.get("status", "active")
            }
            
        except Exception as e:
            print(f"❌ Error getting conversation details: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics"""
        try:
            active_conversations = await self.get_active_conversations()
            waiting_queue = await self.get_waiting_queue()
            
            total_active = len(active_conversations)
            bot_handling = len([c for c in active_conversations if c["status"] == "bot"])
            human_handling = len([c for c in active_conversations if c["status"] == "human"])
            waiting_human = len(waiting_queue)
            
            sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
            for conv in active_conversations:
                sentiment = conv.get("sentiment", "neutral")
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
            
            avg_wait_time = 0
            if waiting_queue:
                total_wait = sum(item["wait_time_seconds"] for item in waiting_queue)
                avg_wait_time = total_wait / len(waiting_queue)
            
            return {
                "success": True,
                "metrics": {
                    "total_active_conversations": total_active,
                    "bot_handling": bot_handling,
                    "human_handling": human_handling,
                    "waiting_for_human": waiting_human,
                    "sentiment_distribution": sentiment_counts,
                    "average_wait_time_seconds": int(avg_wait_time),
                    "active_operators": len([op for op, status in self.operator_status.items() if status == "available"]),
                    "time_window_hours": 6
                },
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error getting metrics: {e}")
            return {"success": False, "error": str(e)}
    
    def _parse_timestamp(self, timestamp) -> datetime.datetime:
        """Parse various timestamp formats"""
        if isinstance(timestamp, str):
            try:
                return datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                return datetime.datetime.now()
        elif hasattr(timestamp, 'timestamp'):
            return datetime.datetime.fromtimestamp(timestamp.timestamp())
        elif hasattr(timestamp, 'seconds'):
            return datetime.datetime.fromtimestamp(timestamp.seconds)
        else:
            return datetime.datetime.now()


# Global instance
live_chat_service = LiveChatService()
