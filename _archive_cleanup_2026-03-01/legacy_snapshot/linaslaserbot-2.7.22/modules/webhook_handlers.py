# -*- coding: utf-8 -*-
"""
Webhook handlers module: Message parsing and processing
Handles webhook reception, parsing, and routing messages to appropriate handlers.
"""

import asyncio
import json
import datetime
import io
import os
import time
from typing import Dict, Any, Optional

from fastapi import Request, HTTPException
import httpx

from modules.core import app, whatsapp_api_client, dashboard_bot_responses
from modules.models import WebhookRequest
import config
from config import WHATSAPP_API_TOKEN
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from utils.utils import get_firestore_db, set_human_takeover_status
from services.api_integrations import log_report_event
from handlers.text_handlers import handle_message, start_command, _delayed_processing_tasks
from handlers.photo_handlers import handle_photo_message
from handlers.voice_handlers import handle_voice_message
from handlers.training_handlers import start_training_mode, exit_training_mode

# Webhook deduplication cache: {message_id: timestamp}
# Prevents processing the same webhook multiple times within a time window
_webhook_dedup_cache = {}
WEBHOOK_DEDUP_WINDOW_SECONDS = 60  # Consider duplicate if received within 60 seconds (Qiscus can send duplicates up to 15+ seconds apart)


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Endpoint for WhatsApp webhook verification."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    if not VERIFY_TOKEN or VERIFY_TOKEN == "YOUR_SECURE_VERIFY_TOKEN":
        raise HTTPException(status_code=500, detail="WHATSAPP_WEBHOOK_VERIFY_TOKEN must be set in .env")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        if challenge is None or (isinstance(challenge, str) and not challenge.strip()):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge")
        try:
            return int(challenge)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge format")
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Endpoint for receiving WhatsApp messages from different providers."""
    _debug = os.getenv("DEBUG_WEBHOOK_LOGGING", "false").lower() == "true"
    if _debug:
        print("\n" + "="*80)
        print("🚨 WEBHOOK HIT DETECTED!")
        print(f"⏰ {datetime.datetime.now()} | IP: {request.client.host if request.client else 'Unknown'}")
        print("="*80)

    try:
        raw_body = await request.body()
        if _debug:
            print(f"📦 Raw body: {len(raw_body)} bytes")

        try:
            webhook_data = json.loads(raw_body.decode('utf-8'))
        except UnicodeDecodeError:
            webhook_data = json.loads(raw_body.decode('utf-8', errors='ignore'))

        if _debug:
            print(f"Provider: {WhatsAppFactory.get_current_provider()} | Data: {json.dumps(webhook_data, ensure_ascii=False)[:500]}...")
        
        current_provider = WhatsAppFactory.get_current_provider()
        adapter = WhatsAppFactory.get_adapter(current_provider)
        if _debug:
            print(f"Adapter: {type(adapter).__name__}")

        parsed_message = adapter.parse_webhook_message(webhook_data)
        if _debug and parsed_message:
            print(f"Parsed: message_id={parsed_message.get('message_id', 'N/A')}")
        
        if not parsed_message:
            print("Trying Meta fallback parser...")
            parsed_message = await handle_meta_webhook(webhook_data)
        
        # Check for duplicate webhooks
        if parsed_message:
            message_id = parsed_message.get("message_id", "")
            current_time = time.time()
            
            # Clean up old entries (older than dedup window)
            expired_keys = [k for k, v in _webhook_dedup_cache.items() if current_time - v > WEBHOOK_DEDUP_WINDOW_SECONDS]
            for k in expired_keys:
                del _webhook_dedup_cache[k]
            
            # Check if this message was recently processed
            if message_id and message_id in _webhook_dedup_cache:
                time_since_last = current_time - _webhook_dedup_cache[message_id]
                print(f"⚠️ DUPLICATE WEBHOOK DETECTED: message_id={message_id} (received {time_since_last:.2f}s ago)")
                print(f"Skipping duplicate processing to prevent duplicate image analysis")
                return {"status": "skipped", "reason": "duplicate_webhook", "message_id": message_id}
            
            # Record this message as processed
            if message_id:
                _webhook_dedup_cache[message_id] = current_time
                print(f"✅ Webhook recorded in dedup cache: {message_id}")
        
        if parsed_message:
            print(f"Processing parsed message: {parsed_message}")
            # IMPORTANT: Process in background so we return 200 immediately.
            # MontyMobile throttles/backs off if webhook responses are slow.
            asyncio.ensure_future(process_parsed_message(parsed_message, adapter))
            print("Message queued for processing (background)")
        else:
            print("ERROR: Could not parse webhook from any provider")

        return {"status": "success"}
        
    except Exception as e:
        print(f"CRITICAL ERROR processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


async def handle_meta_webhook(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle Meta/WhatsApp Cloud API webhook format (fallback)"""
    try:
        request_body = WebhookRequest(**webhook_data)
        
        for entry in request_body.entry:
            for change in entry.changes:
                if change.field == "messages" and change.value.messages:
                    for message in change.value.messages:
                        user_whatsapp_id = message.from_
                        user_name = next((c.profile.name for c in change.value.contacts if c.wa_id == user_whatsapp_id), user_whatsapp_id)
                        
                        return {
                            "user_id": user_whatsapp_id,
                            "user_name": user_name,
                            "message_id": message.id,
                            "timestamp": message.timestamp,
                            "type": message.type,
                            "content": extract_meta_message_content(message)
                        }
        return None
    except Exception as e:
        print(f"Error parsing Meta webhook: {e}")
        return None


def extract_meta_message_content(message) -> Dict[str, Any]:
    """Extract content from Meta message format"""
    if message.type == "text":
        return {"text": message.text.body}
    elif message.type == "image":
        return {"image_id": message.image.id, "caption": getattr(message.image, 'caption', None)}
    elif message.type == "audio":
        return {"audio_id": message.audio.id}
    elif message.type == "video":
        return {"video_id": message.video.id, "caption": getattr(message.video, 'caption', None)}
    elif message.type == "document":
        return {"document_id": message.document.id, "filename": getattr(message.document, 'filename', None)}
    else:
        return {"raw": message.model_dump()}


async def process_parsed_message(parsed_message: Dict[str, Any], adapter):
    """Process a parsed message regardless of provider"""
    user_id = parsed_message["user_id"]
    user_name = parsed_message["user_name"]
    message_type = parsed_message["type"]
    content = parsed_message["content"]
    phone_number = parsed_message.get("phone_number")
    
    print(f"DEBUG: Processing message - user_id: {user_id}, phone_number: {phone_number}")
    
    # Initialize user_data_whatsapp if not exists
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            'user_preferred_lang': 'ar', 
            'initial_user_query_to_process': None, 
            'awaiting_human_handover_confirmation': False, 
            'current_conversation_id': None
        }
        print(f"✅ Initialized user_data_whatsapp for user {user_id}")
    
    # Store phone number IMMEDIATELY
    if phone_number:
        config.user_data_whatsapp[user_id]["phone_number"] = phone_number
        print(f"✅ CRITICAL: Stored phone_number {phone_number} for user {user_id} BEFORE any processing")
    else:
        print(f"⚠️ WARNING: No phone_number extracted for user {user_id}")

    # Persist source message id as one-shot metadata for Firestore dedupe.
    source_message_id = parsed_message.get("message_id")
    if source_message_id:
        config.user_data_whatsapp[user_id]["_source_message_id"] = str(source_message_id)
    else:
        config.user_data_whatsapp[user_id].pop("_source_message_id", None)

    # ===== RESTORE USER STATE FROM FIRESTORE FIRST (handles server restart) =====
    # Always try to restore from Firestore before API lookup
    # Only restore if gender is not already set to a valid value
    current_gender = config.user_gender.get(user_id)
    print(f"🔍 DEBUG: Before Firestore restore - current_gender in memory: '{current_gender}'")
    if current_gender not in ["male", "female"]:
        try:
            from utils.utils import get_user_state_from_firestore
            print(f"🔄 Attempting to restore user state from Firestore for {user_id}...")
            firestore_state = await get_user_state_from_firestore(user_id)
            print(f"🔍 DEBUG: Firestore returned state: {firestore_state}")

            if firestore_state:
                # Restore gender if valid
                firestore_gender = firestore_state.get("gender", "")
                if firestore_gender in ["male", "female"]:
                    config.user_gender[user_id] = firestore_gender
                    print(f"✅ Restored gender from Firestore: {firestore_gender}")

                # Restore greeting stage if > 0
                firestore_greeting_stage = firestore_state.get("greeting_stage", 0)
                if firestore_greeting_stage > 0:
                    config.user_greeting_stage[user_id] = firestore_greeting_stage
                    print(f"✅ Restored greeting_stage from Firestore: {firestore_greeting_stage}")

                # Restore name if available
                firestore_name = firestore_state.get("name", "")
                if firestore_name and firestore_name != "Unknown Customer":
                    config.user_names[user_id] = firestore_name
                    user_name = firestore_name
                    print(f"✅ Restored name from Firestore: {firestore_name}")
            else:
                print(f"ℹ️ No user state found in Firestore for {user_id}")
        except Exception as e:
            print(f"❌ Error restoring user state from Firestore: {e}")
            import traceback
            traceback.print_exc()

    # Debug: Log state after Firestore restoration attempt
    print(f"🔍 DEBUG: After Firestore restore - gender: '{config.user_gender.get(user_id)}', greeting_stage: {config.user_greeting_stage.get(user_id, 0)}")

    # Fetch customer data from API ONLY if Firestore didn't have valid gender
    current_gender_after_firestore = config.user_gender.get(user_id)
    if current_gender_after_firestore not in ["male", "female"] and phone_number:
        try:
            from services.api_integrations import get_customer_by_phone
            
            phone_clean = str(phone_number).replace("+", "").replace(" ", "").replace("-", "")
            if phone_clean.startswith("961"):
                phone_clean = phone_clean[3:]
            
            print(f"🔍 Fetching customer data from API for phone: {phone_clean}")
            
            customer_response = await get_customer_by_phone(phone=phone_clean)
            
            if customer_response and customer_response.get("success") and customer_response.get("data"):
                customer_data = customer_response["data"]
                print(f"✅ Customer found in API: {customer_data}")
                
                if customer_data.get("name"):
                    config.user_names[user_id] = customer_data["name"]
                    user_name = customer_data["name"]
                    print(f"✅ Updated user name from API: {user_name}")
                
                if customer_data.get("gender"):
                    api_gender = customer_data["gender"].lower()
                    if api_gender in ["male", "female"]:
                        config.user_gender[user_id] = api_gender
                        print(f"✅ Updated gender from API: {api_gender}")
                        
                        if config.user_greeting_stage.get(user_id, 0) <= 1:
                            config.user_greeting_stage[user_id] = 2
                            print(f"✅ Set greeting stage to 2 (skip gender question)")
            else:
                print(f"ℹ️ Customer not found in API for phone: {phone_clean}")
                
        except Exception as e:
            print(f"❌ Error fetching customer from API: {e}")
            import traceback
            traceback.print_exc()

    # Initialize user state ONLY for NEW users
    is_new_user = (
        user_id not in config.user_names or
        user_id not in config.user_greeting_stage or
        config.user_greeting_stage.get(user_id, 0) == 0
    )
    
    if is_new_user:
        print(f"🆕 NEW USER detected: {user_id}, calling start_command_whatsapp...")
        await start_command_whatsapp(user_id, user_name)
    else:
        print(f"👤 EXISTING USER: {user_id}, skipping start_command_whatsapp")

    # Handle different message types
    if message_type == "text":
        # Handle both dict format (old) and string format (new)
        if isinstance(content, dict):
            user_input_text = content.get("text", "")
        else:
            user_input_text = str(content)
        
        if user_input_text.lower() == "/start":
            await start_command_whatsapp(user_id, user_name)
        elif user_input_text.lower() == "/train":
            await start_training_mode_whatsapp(user_id)
        elif user_input_text.lower() == "/exit":
            await exit_training_mode_whatsapp(user_id)
        elif user_input_text.lower() == "/daily_report":
            await generate_daily_report_command_whatsapp(user_id)
        elif user_input_text.lower() == "/takeover":
            current_conv_id = config.user_data_whatsapp[user_id].get('current_conversation_id')
            if current_conv_id:
                await set_human_takeover_status(user_id, current_conv_id, True)
                await adapter.send_text_message(user_id, "تم تفعيل وضع التحكم البشري لهذه المحادثة. البوت لن يرد عليها.")
            else:
                await adapter.send_text_message(user_id, "لا توجد محادثة جارية لتفعيل التحكم البشري عليها.")
        elif user_input_text.lower() == "/release":
            current_conv_id = config.user_data_whatsapp[user_id].get('current_conversation_id')
            if current_conv_id:
                await set_human_takeover_status(user_id, current_conv_id, False)
                await adapter.send_text_message(user_id, "تم إلغاء وضع التحكم البشري لهذه المحادثة. البوت سيعود للرد.")
            else:
                await adapter.send_text_message(user_id, "لا توجد محادثة جارية لإلغاء التحكم البشري عليها.")
        else:
            await handle_message_whatsapp_with_adapter(user_id, user_input_text, user_name, adapter, phone_number)
            
    elif message_type == "image":
        image_id = content.get("image_id")
        if image_id:
            # Process image with GPT-4 Vision analysis for all providers
            print(f"DEBUG: Image received - processing with GPT-4 Vision analysis")
            await handle_photo_message_whatsapp_with_adapter(user_id, image_id, user_name, adapter)
            
    elif message_type == "audio":
        audio_id = content.get("audio_id")
        if audio_id:
            await handle_voice_message_whatsapp_with_adapter(user_id, audio_id, user_name, adapter)
            
    elif message_type == "file_attachment":
        file_url = content.get("image_id") or content.get("audio_id") or content.get("document_id")
        if file_url:
            if content.get("image_id"):
                await handle_photo_message_whatsapp_with_adapter(user_id, file_url, user_name, adapter)
            elif content.get("audio_id"):
                await handle_voice_message_whatsapp_with_adapter(user_id, file_url, user_name, adapter)
            else:
                await adapter.send_text_message(user_id, "تم استلام الملف، شكراً لك!")
                
    else:
        await adapter.send_text_message(user_id, "عذراً، أنا أستطيع معالجة الرسائل النصية، الصور، والرسائل الصوتية فقط حالياً. 😅")
        print(f"Unhandled message type: {message_type} from {user_id}")

    # Clear one-shot source ID if it wasn't consumed in handlers.
    config.user_data_whatsapp.get(user_id, {}).pop("_source_message_id", None)


# ============================================================================
# WhatsApp Adapter Functions
# ============================================================================

# Import these after function definitions to avoid circular imports
import datetime
from config import TRAINER_WHATSAPP_NUMBER
from services.api_integrations import generate_daily_report_command


async def start_command_whatsapp(user_whatsapp_id: str, user_name: str):
    """Adapts start_command for WhatsApp."""
    print(f"DEBUG: start_command_whatsapp called for user {user_whatsapp_id}")

    config.user_names[user_whatsapp_id] = user_name

    config.user_context[user_whatsapp_id].clear()
    config.gender_attempts[user_whatsapp_id] = 0
    config.user_last_bot_response_time[user_whatsapp_id] = datetime.datetime.now()
    config.user_in_training_mode[user_whatsapp_id] = False
    config.user_photo_analysis_count[user_whatsapp_id] = 0
    config.user_in_human_takeover_mode[user_whatsapp_id] = False

    # FIX: Use .get() to properly check for existing gender value
    # This preserves gender that was set from API in process_parsed_message
    existing_gender = config.user_gender.get(user_whatsapp_id)
    if existing_gender and existing_gender in ["male", "female"]:
        config.user_greeting_stage[user_whatsapp_id] = 2  # Skip gender question
        print(f"✅ Gender already set (preserving): {existing_gender}")
    else:
        config.user_gender[user_whatsapp_id] = "unknown"  # Use "unknown" for consistency
        config.user_greeting_stage[user_whatsapp_id] = 1  # Ask for gender
        print(f"ℹ️ Gender not found, will ask user")

    if user_whatsapp_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_whatsapp_id] = {}

    config.user_data_whatsapp[user_whatsapp_id]['user_preferred_lang'] = 'ar'
    config.user_data_whatsapp[user_whatsapp_id]['initial_user_query_to_process'] = None
    config.user_data_whatsapp[user_whatsapp_id]['awaiting_human_handover_confirmation'] = False
    config.user_data_whatsapp[user_whatsapp_id]['current_conversation_id'] = None

    initial_message = config.WELCOME_MESSAGES.get(
        config.user_data_whatsapp[user_whatsapp_id]['user_preferred_lang'],
        config.WELCOME_MESSAGES['ar']
    )

    # Use current provider's adapter (MontyMobile/Meta/etc.) - not hardcoded Meta
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)
    await adapter.send_text_message(user_whatsapp_id, initial_message)

    # NOTE: Removed call to start_command() to prevent:
    # 1. Duplicate welcome messages
    # 2. Potential gender reset
    # All initialization is now done in this function

    print(f"DEBUG: start_command_whatsapp ended for user {user_whatsapp_id}. Stage: {config.user_greeting_stage[user_whatsapp_id]}, Gender: '{config.user_gender.get(user_whatsapp_id, 'unknown')}'")


async def handle_message_whatsapp_with_adapter(user_id: str, user_input_text: str, user_name: str, adapter, phone_number: str = None):
    """Handle message with specific adapter"""
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            'user_preferred_lang': 'ar', 
            'initial_user_query_to_process': None, 
            'awaiting_human_handover_confirmation': False, 
            'current_conversation_id': None
        }

    if phone_number:
        config.user_data_whatsapp[user_id]['phone_number'] = phone_number
        print(f"✅ DEBUG: Stored phone_number {phone_number} for user {user_id}")
    else:
        print(f"❌ CRITICAL: No phone_number extracted for user {user_id}!")
        config.user_data_whatsapp[user_id]['phone_number'] = None

    async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
        if message_text:
            return await adapter.send_text_message(to_number, message_text)
        elif image_url:
            return await adapter.send_image_message(to_number, image_url)
        elif audio_url:
            return await adapter.send_audio_message(to_number, audio_url)
        return False

    from modules.whatsapp_adapters import send_whatsapp_typing_indicator
    await handle_message(
        user_id=user_id,
        user_name=user_name,
        user_input_text=user_input_text,
        user_data=config.user_data_whatsapp[user_id],
        send_message_func=adapter_send_message,
        send_action_func=send_whatsapp_typing_indicator
    )


async def handle_photo_message_whatsapp_with_adapter(user_id: str, image_id: str, user_name: str, adapter):
    """Handle photo message with specific adapter"""
    try:
        current_provider = WhatsAppFactory.get_current_provider()
        
        print(f"DEBUG: Handling photo message - provider: {current_provider}, image_id: {image_id}")
        
        if current_provider == "qiscus":
            print(f"DEBUG: Using Qiscus provider - image_id is URL")
            image_url = image_id
        elif current_provider == "montymobile":
            print(f"DEBUG: Using MontyMobile provider - downloading media via MontyMobile API")
            
            # Use MontyMobile's media download endpoint
            # Based on their documentation: GET https://notification-qa.montylocal.net/api/v1/Push/external/{media_id}
            # Production endpoint should be similar pattern
            try:
                # MontyMobile media download endpoint (CORRECT - as provided by MontyMobile support)
                media_api_url = f"{adapter.base_url}/api/v2/WhatsappApi/get-media?MediaId={image_id}"
                
                montymobile_headers = {
                    "Tenant": adapter.tenant_id,
                    "api-key": adapter.api_token
                }
                
                print(f"DEBUG: Downloading media from MontyMobile API: {media_api_url}")
                print(f"DEBUG: Using Tenant: {adapter.tenant_id}")
                
                async with httpx.AsyncClient() as client:
                    # Download the media file directly
                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
                    media_response.raise_for_status()
                    
                    # Detect image format from content-type header or magic bytes
                    content_type = media_response.headers.get('content-type', '').lower()
                    print(f"DEBUG: Media response content-type: {content_type}")
                    print(f"DEBUG: Media response size: {len(media_response.content)} bytes")
                    
                    # Check if response is JSON (MontyMobile returns JSON with image data inside)
                    if 'application/json' in content_type:
                        print(f"DEBUG: Response is JSON, extracting image data...")
                        media_json = media_response.json()
                        print(f"DEBUG: JSON keys: {list(media_json.keys())}")
                        
                        # Extract the actual image data from JSON
                        # MontyMobile might return base64 data or a URL
                        if 'data' in media_json:
                            image_data_field = media_json['data']
                            if isinstance(image_data_field, str):
                                # It's base64 encoded
                                import base64
                                image_bytes = base64.b64decode(image_data_field)
                                print(f"DEBUG: Decoded base64 image from JSON, size: {len(image_bytes)} bytes")
                            elif isinstance(image_data_field, dict):
                                # It's a nested object, check for base64 or URL inside
                                print(f"DEBUG: data field is dict with keys: {list(image_data_field.keys())}")
                                # MontyMobile returns {"data": {"data": "base64string"}}
                                if 'data' in image_data_field and isinstance(image_data_field['data'], str):
                                    # The actual base64 data is in data.data
                                    import base64
                                    image_bytes = base64.b64decode(image_data_field['data'])
                                    print(f"DEBUG: Decoded base64 image from nested data.data, size: {len(image_bytes)} bytes")
                                elif 'base64' in image_data_field or 'content' in image_data_field or 'file' in image_data_field:
                                    # Try different possible field names
                                    base64_data = image_data_field.get('base64') or image_data_field.get('content') or image_data_field.get('file')
                                    if base64_data:
                                        import base64
                                        image_bytes = base64.b64decode(base64_data)
                                        print(f"DEBUG: Decoded base64 image from nested JSON, size: {len(image_bytes)} bytes")
                                    else:
                                        print(f"DEBUG: Full data object: {json.dumps(image_data_field, indent=2)[:500]}...")
                                        raise ValueError(f"Could not find base64 data in nested object")
                                elif 'url' in image_data_field:
                                    image_url_from_json = image_data_field['url']
                                    print(f"DEBUG: Found URL in nested data object, downloading from: {image_url_from_json}")
                                    image_response = await client.get(image_url_from_json, timeout=30)
                                    image_response.raise_for_status()
                                    image_bytes = image_response.content
                                else:
                                    print(f"DEBUG: Full data object: {json.dumps(image_data_field, indent=2)}")
                                    raise ValueError(f"Could not find image data in nested object")
                            else:
                                print(f"DEBUG: Unexpected data format in JSON: {type(image_data_field)}")
                                raise ValueError(f"Unexpected image data format in JSON response")
                        elif 'url' in media_json:
                            # It's a URL, download from there
                            image_url_from_json = media_json['url']
                            print(f"DEBUG: Found URL in JSON, downloading from: {image_url_from_json}")
                            image_response = await client.get(image_url_from_json, timeout=30)
                            image_response.raise_for_status()
                            image_bytes = image_response.content
                        else:
                            print(f"DEBUG: Full JSON response: {json.dumps(media_json, indent=2)}")
                            raise ValueError(f"Could not find image data in JSON response")
                    else:
                        # Response is raw binary image
                        image_bytes = media_response.content
                        print(f"DEBUG: Response is raw binary image")
                    
                    # Detect format from magic bytes (first few bytes of file)
                    magic_bytes = image_bytes[:8]
                    print(f"DEBUG: First 8 bytes (hex): {magic_bytes.hex()}")
                    
                    # Determine image format
                    if magic_bytes.startswith(b'\xff\xd8\xff'):
                        image_format = 'jpeg'
                    elif magic_bytes.startswith(b'\x89PNG'):
                        image_format = 'png'
                    elif magic_bytes.startswith(b'GIF87a') or magic_bytes.startswith(b'GIF89a'):
                        image_format = 'gif'
                    elif magic_bytes.startswith(b'RIFF') and magic_bytes[8:12] == b'WEBP':
                        image_format = 'webp'
                    else:
                        # Fallback to content-type
                        if 'jpeg' in content_type or 'jpg' in content_type:
                            image_format = 'jpeg'
                        elif 'png' in content_type:
                            image_format = 'png'
                        elif 'gif' in content_type:
                            image_format = 'gif'
                        elif 'webp' in content_type:
                            image_format = 'webp'
                        else:
                            image_format = 'jpeg'  # Default fallback
                    
                    print(f"DEBUG: Detected image format: {image_format}")
                    
                    # Convert to base64 for processing (use image_bytes, not media_response.content!)
                    import base64
                    base64_image = base64.b64encode(image_bytes).decode("utf-8")
                    print(f"DEBUG: Encoded image to base64, size: {len(base64_image)} bytes")
                    
                    # Create a data URL for the photo handler with correct format
                    image_url = f"data:image/{image_format};base64,{base64_image}"
                    print(f"DEBUG: Created base64 data URL for image processing with format: {image_format}")
                    
            except Exception as e:
                print(f"ERROR: Failed to download media from MontyMobile: {e}")
                import traceback
                traceback.print_exc()
                raise
        else:
            print(f"DEBUG: Using Meta/Facebook provider - fetching from Graph API")
            response = await whatsapp_api_client.get(f"/{image_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"})
            response.raise_for_status()
            image_data = response.json()
            image_url = image_data.get("url")
            if not image_url:
                raise ValueError("Image URL not found in API response.")

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar', 
                'initial_user_query_to_process': None, 
                'awaiting_human_handover_confirmation': False, 
                'current_conversation_id': None
            }

        async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            if message_text:
                return await adapter.send_text_message(to_number, message_text)
            elif image_url:
                return await adapter.send_image_message(to_number, image_url)
            elif audio_url:
                return await adapter.send_audio_message(to_number, audio_url)
            return False

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        await handle_photo_message(
            user_id=user_id,
            user_name=user_name,
            image_url=image_url,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=adapter_send_message,
            send_action_func=send_whatsapp_typing_indicator
        )

    except Exception as e:
        print(f"ERROR processing image {image_id} for user {user_id}: {e}")
        await adapter.send_text_message(user_id, "عذراً، واجهت مشكلة في معالجة صورتك. الرجاء المحاولة مرة أخرى.")
        log_report_event("whatsapp_media_download_failed", user_name, config.user_gender.get(user_id, "unspecified"), {"media_type": "image", "error": str(e)})


async def handle_voice_message_whatsapp_with_adapter(user_id: str, audio_id: str, user_name: str, adapter):
    """Handle voice message with specific adapter"""
    try:
        current_provider = WhatsAppFactory.get_current_provider()
        
        print(f"DEBUG: Handling audio message - provider: {current_provider}, audio_id: {audio_id}")
        
        # Extract audio URL based on provider
        audio_url = None
        if current_provider == "qiscus":
            # For Qiscus, audio_id IS the full URL
            print(f"DEBUG: Using Qiscus provider - audio_id is URL")
            audio_url = audio_id
            async with httpx.AsyncClient() as client:
                audio_content_response = await client.get(audio_id)
                audio_content_response.raise_for_status()
                audio_data_bytes = io.BytesIO(audio_content_response.content)
                audio_data_bytes.seek(0)
        elif current_provider == "montymobile":
            print(f"DEBUG: Using MontyMobile provider - downloading audio via MontyMobile API")
            
            try:
                # MontyMobile media download endpoint (same as images)
                media_api_url = f"{adapter.base_url}/api/v2/WhatsappApi/get-media?MediaId={audio_id}"
                
                montymobile_headers = {
                    "Tenant": adapter.tenant_id,
                    "api-key": adapter.api_token
                }
                
                print(f"DEBUG: Downloading audio from MontyMobile API: {media_api_url}")
                print(f"DEBUG: Using Tenant: {adapter.tenant_id}")
                
                async with httpx.AsyncClient() as client:
                    # Download the media file
                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
                    media_response.raise_for_status()
                    
                    content_type = media_response.headers.get('content-type', '').lower()
                    print(f"DEBUG: Audio response content-type: {content_type}")
                    print(f"DEBUG: Audio response size: {len(media_response.content)} bytes")
                    
                    # Check if response is JSON (MontyMobile returns JSON with audio data inside)
                    if 'application/json' in content_type:
                        print(f"DEBUG: Response is JSON, extracting audio data...")
                        media_json = media_response.json()
                        print(f"DEBUG: JSON keys: {list(media_json.keys())}")
                        
                        # Extract the actual audio data from JSON (same structure as images)
                        if 'data' in media_json:
                            audio_data_field = media_json['data']
                            if isinstance(audio_data_field, str):
                                # It's base64 encoded
                                import base64
                                audio_bytes = base64.b64decode(audio_data_field)
                                print(f"DEBUG: Decoded base64 audio from JSON, size: {len(audio_bytes)} bytes")
                            elif isinstance(audio_data_field, dict):
                                # It's a nested object
                                print(f"DEBUG: data field is dict with keys: {list(audio_data_field.keys())}")
                                # MontyMobile returns {"data": {"data": "base64string"}}
                                if 'data' in audio_data_field and isinstance(audio_data_field['data'], str):
                                    # The actual base64 data is in data.data
                                    import base64
                                    audio_bytes = base64.b64decode(audio_data_field['data'])
                                    print(f"DEBUG: Decoded base64 audio from nested data.data, size: {len(audio_bytes)} bytes")
                                elif 'url' in audio_data_field:
                                    audio_url_from_json = audio_data_field['url']
                                    print(f"DEBUG: Found URL in nested data object, downloading from: {audio_url_from_json}")
                                    audio_response = await client.get(audio_url_from_json, timeout=30)
                                    audio_response.raise_for_status()
                                    audio_bytes = audio_response.content
                                else:
                                    print(f"DEBUG: Full data object: {json.dumps(audio_data_field, indent=2)[:500]}...")
                                    raise ValueError(f"Could not find audio data in nested object")
                            else:
                                print(f"DEBUG: Unexpected data format in JSON: {type(audio_data_field)}")
                                raise ValueError(f"Unexpected audio data format in JSON response")
                        elif 'url' in media_json:
                            # It's a URL, download from there
                            audio_url_from_json = media_json['url']
                            print(f"DEBUG: Found URL in JSON, downloading from: {audio_url_from_json}")
                            audio_response = await client.get(audio_url_from_json, timeout=30)
                            audio_response.raise_for_status()
                            audio_bytes = audio_response.content
                        else:
                            print(f"DEBUG: Full JSON response: {json.dumps(media_json, indent=2)[:500]}...")
                            raise ValueError(f"Could not find audio data in JSON response")
                    else:
                        # Response is raw binary audio
                        audio_bytes = media_response.content
                        print(f"DEBUG: Response is raw binary audio")
                    
                    # Create BytesIO object for audio processing
                    audio_data_bytes = io.BytesIO(audio_bytes)
                    audio_data_bytes.seek(0)
                    print(f"DEBUG: Created BytesIO object for audio processing")

                    # Upload audio to Firebase Storage to get a playable URL for the dashboard
                    try:
                        import base64
                        from utils.utils import upload_base64_to_firebase_storage

                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        file_name = f"voice_{user_id}_{audio_id[:8]}.ogg"

                        audio_url = await upload_base64_to_firebase_storage(
                            audio_base64,
                            file_name,
                            file_type="audio/ogg"
                        )

                        if audio_url:
                            print(f"DEBUG: Uploaded audio to Firebase Storage: {audio_url}")
                        else:
                            print(f"DEBUG: Failed to upload audio to Firebase Storage, audio_url will be None")
                    except Exception as upload_error:
                        print(f"WARNING: Failed to upload audio to Firebase Storage: {upload_error}")
                        audio_url = None
                    
            except Exception as e:
                print(f"ERROR: Failed to download audio from MontyMobile: {e}")
                import traceback
                traceback.print_exc()
                raise
        else:
            # For Meta/360Dialog, get URL from API response
            print(f"DEBUG: Using Meta/Facebook provider - fetching from Graph API")
            response = await whatsapp_api_client.get(f"/{audio_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"})
            response.raise_for_status()
            audio_data = response.json()
            audio_url = audio_data.get("url")
            if not audio_url:
                raise ValueError("Audio URL not found in API response.")

            async with httpx.AsyncClient() as client:
                audio_content_response = await client.get(audio_url)
                audio_content_response.raise_for_status()
                audio_data_bytes = io.BytesIO(audio_content_response.content)
                audio_data_bytes.seek(0)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar', 
                'initial_user_query_to_process': None, 
                'awaiting_human_handover_confirmation': False, 
                'current_conversation_id': None
            }

        async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            if message_text:
                return await adapter.send_text_message(to_number, message_text)
            elif image_url:
                return await adapter.send_image_message(to_number, image_url)
            elif audio_url:
                return await adapter.send_audio_message(to_number, audio_url)
            return False

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        # ✅ CRITICAL FIX: Pass audio_url to handle_voice_message so it gets saved to Firebase
        await handle_voice_message(
            user_id=user_id,
            user_name=user_name,
            audio_data_bytes=audio_data_bytes,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=adapter_send_message,
            send_action_func=send_whatsapp_typing_indicator,
            audio_url=audio_url  # ✅ NEW: Pass the URL so voice message has type="voice" + audio_url in Firebase
        )

    except Exception as e:
        print(f"ERROR processing audio {audio_id} for user {user_id}: {e}")
        await adapter.send_text_message(user_id, "عذراً، واجهت مشكلة في معالجة رسالتك الصوتية. الرجاء المحاولة مرة أخرى.")
        log_report_event("whatsapp_media_download_failed", user_name, config.user_gender.get(user_id, "unspecified"), {"media_type": "audio", "error": str(e)})


async def start_training_mode_whatsapp(user_whatsapp_id: str):
    """Adapts start_training_mode for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str = None, img: str = None, aud: str = None):
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        if user_whatsapp_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_whatsapp_id] = {'user_preferred_lang': 'ar', 'initial_user_query_to_process': None, 'awaiting_human_handover_confirmation': False, 'current_conversation_id': None}

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        await start_training_mode(
            user_id=user_whatsapp_id,
            user_data=config.user_data_whatsapp[user_whatsapp_id],
            send_message_func=_adapter_send,
            send_action_func=send_whatsapp_typing_indicator
        )
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لتفعيل وضع التدريب.")


async def exit_training_mode_whatsapp(user_whatsapp_id: str):
    """Adapts exit_training_mode for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str = None, img: str = None, aud: str = None):
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        if user_whatsapp_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_whatsapp_id] = {'user_preferred_lang': 'ar', 'initial_user_query_to_process': None, 'awaiting_human_handover_confirmation': False, 'current_conversation_id': None}

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        await exit_training_mode(
            user_id=user_whatsapp_id,
            user_data=config.user_data_whatsapp[user_whatsapp_id],
            send_message_func=_adapter_send,
            send_action_func=send_whatsapp_typing_indicator
        )
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لإلغاء تفعيل وضع التدريب.")


async def generate_daily_report_command_whatsapp(user_whatsapp_id: str):
    """Adapts generate_daily_report_command for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str = None, img: str = None, aud: str = None):
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        await adapter.send_text_message(user_whatsapp_id, "جارٍ توليد التقرير اليومي... 📊")

        try:
            await generate_daily_report_command(
                user_id=user_whatsapp_id,
                send_message_func=_adapter_send
            )
        except Exception as e:
            print(f"ERROR generating daily report for {user_whatsapp_id}: {e}")
            await adapter.send_text_message(user_whatsapp_id, f"حدث خطأ أثناء توليد التقرير: {str(e)}")
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لطلب التقرير اليومي.")


async def send_whatsapp_typing_indicator(user_whatsapp_id: str):
    """Sends a typing indicator to WhatsApp."""
    print(f"DEBUG: WhatsApp typing indicator for {user_whatsapp_id} (simulated).\n")
