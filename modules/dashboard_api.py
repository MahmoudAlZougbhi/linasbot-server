# -*- coding: utf-8 -*-
"""
Dashboard API module: Testing and simulation endpoints
Provides endpoints for dashboard testing of the bot functionality.
"""

import datetime
import base64
import tempfile
import os
import io
import json
from typing import Dict, Any

from fastapi import File, UploadFile, Form
import httpx

from modules.core import app, dashboard_stats, dashboard_bot_responses
from modules.models import (
    TestMessageRequest, 
    TestImageRequest, 
    TestVoiceRequest,
    ProviderSwitchRequest
)
import config
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from handlers.text_handlers import handle_message, _delayed_processing_tasks
from handlers.photo_handlers import handle_photo_message
from handlers.voice_handlers import handle_voice_message
from modules.whatsapp_adapters import send_whatsapp_typing_indicator


async def dashboard_send_message_capture(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
    """Capture bot responses for dashboard display"""
    if message_text:
        if to_number not in dashboard_bot_responses:
            dashboard_bot_responses[to_number] = []
        dashboard_bot_responses[to_number].append(message_text)
        print(f"Dashboard captured bot response for {to_number}: {message_text}")
    return True


@app.get("/")
async def root():
    return {"message": "Lina's Laser AI Bot is running!"}


@app.get("/api/test")
async def test_api():
    """Test endpoint for dashboard health check"""
    return {
        "status": "online",
        "message": "Lina's Laser AI Bot is running!",
        "features": [
            "Text Chat",
            "Voice Processing", 
            "Image Analysis",
            "Multi-Provider WhatsApp",
            "Q&A Management"
        ],
        "current_provider": WhatsAppFactory.get_current_provider(),
        "timestamp": datetime.datetime.now().isoformat()
    }


@app.post("/api/switch-provider")
async def switch_provider(request: ProviderSwitchRequest):
    """Switch WhatsApp provider"""
    try:
        adapter = WhatsAppFactory.switch_provider(request.provider)
        return {
            "success": True,
            "message": f"Switched to {request.provider}",
            "current_provider": WhatsAppFactory.get_current_provider()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-message")
async def test_message(request: TestMessageRequest):
    """Send a test message through the bot"""
    try:
        start_time = datetime.datetime.now()
        
        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print(f"=== DASHBOARD TEST ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Adapter type: {type(adapter).__name__}")
            print(f"Current provider: {WhatsAppFactory.get_current_provider()}")
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {request.provider}: {str(e)}"}
        
        if request.provider == "qiscus":
            user_id = f"test_room_{request.phone}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[request.phone] = user_id
        else:
            user_id = request.phone
            
        user_name = f"Test User ({request.phone})"
        
        dashboard_bot_responses.pop(user_id, None)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }
        
        async def handle_message_dashboard(user_whatsapp_id: str, user_input_text: str, user_name: str):
            """Dashboard version that captures bot responses WITHOUT saving to Firebase"""
            if user_whatsapp_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_whatsapp_id] = {
                    'user_preferred_lang': 'ar', 
                    'initial_user_query_to_process': None, 
                    'awaiting_human_handover_confirmation': False, 
                    'current_conversation_id': None
                }

            # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
            # config.TESTING_MODE = True
            # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_whatsapp_id}")

            async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
                await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
                
                if request.provider == "qiscus":
                    try:
                        print(f"DEBUG: Testing Qiscus send with room_id: {to_number}")
                        result = await adapter.send_text_message(to_number, message_text)
                        print(f"DEBUG: Qiscus send result: {result}")
                    except Exception as e:
                        print(f"DEBUG: Qiscus send failed (expected in test): {e}")
                
                return True

            try:
                await handle_message(
                    user_id=user_whatsapp_id,
                    user_name=user_name,
                    user_input_text=user_input_text,
                    user_data=config.user_data_whatsapp[user_whatsapp_id],
                    send_message_func=capture_send_message,
                    send_action_func=send_whatsapp_typing_indicator
                )
            finally:
                # config.TESTING_MODE = False
                # print(f"🧪 TESTING MODE DISABLED - Firebase saving re-enabled")
                pass

        print(f"DEBUG: Processing message '{request.message}' for user {user_id}")
        
        try:
            await handle_message_dashboard(user_id, request.message, user_name)
            print(f"DEBUG: Message processing completed for user {user_id}")
        except Exception as e:
            print(f"DEBUG: Error in handle_message_dashboard: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for any delayed processing tasks to complete
        import asyncio
        if user_id in _delayed_processing_tasks:
            print(f"DEBUG: Waiting for delayed task for user {user_id} to complete...")
            try:
                await _delayed_processing_tasks[user_id]
                print(f"DEBUG: Delayed task completed for user {user_id}")
            except Exception as e:
                print(f"DEBUG: Delayed task error: {e}")
            finally:
                # Clean up the task
                if user_id in _delayed_processing_tasks:
                    del _delayed_processing_tasks[user_id]
        else:
            print(f"DEBUG: No delayed task found for user {user_id}")
        
        captured_responses = dashboard_bot_responses.get(user_id, [])
        print(f"DEBUG: Captured responses for {user_id}: {captured_responses}")
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = "No response captured - check console for errors"
        
        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        dashboard_stats["conversations"].append({
            "user": user_name,
            "message": request.message,
            "bot_response": bot_response,
            "timestamp": start_time.isoformat(),
            "provider": request.provider
        })
        
        return {
            "success": True,
            "message": "Test message processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "provider_info": {
                "provider": request.provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-image")
async def test_image(request: TestImageRequest):
    """Test image analysis through the bot with image URL"""
    try:
        start_time = datetime.datetime.now()
        
        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print(f"=== IMAGE URL TEST ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Image URL: {request.image_url}")
            print(f"Caption: {request.caption}")
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {request.provider}: {str(e)}"}
        
        if request.provider == "qiscus":
            user_id = f"test_room_{request.phone}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[request.phone] = user_id
        else:
            user_id = request.phone
            
        user_name = f"Test User ({request.phone})"
        
        dashboard_bot_responses.pop(user_id, None)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }
        
        # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
        # config.TESTING_MODE = True
        # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_id}")

        async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        try:
            await handle_photo_message(
                user_id=user_id,
                user_name=user_name,
                image_url=request.image_url,
                user_data=config.user_data_whatsapp[user_id],
                send_message_func=capture_send_message,
                send_action_func=send_whatsapp_typing_indicator
            )
        finally:
            # config.TESTING_MODE = False
            # print(f"🧪 TESTING MODE DISABLED - Firebase saving re-enabled")
            pass

        captured_responses = dashboard_bot_responses.get(user_id, [])
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = "No response captured - check console for errors"
        
        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        dashboard_stats["conversations"].append({
            "user": user_name,
            "message": f"[Image: {request.image_url}] {request.caption}",
            "bot_response": bot_response,
            "timestamp": start_time.isoformat(),
            "provider": request.provider
        })
        
        return {
            "success": True,
            "message": "Test image processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "provider_info": {
                "provider": request.provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-voice")
async def test_voice(
    audio: UploadFile = File(None),
    phone: str = Form(None),
    provider: str = Form(None),
    voice_text: str = Form(None)
):
    """Test voice message processing - handles both file upload and text simulation"""
    try:
        # Check if this is a file upload
        if audio is not None and audio.filename:
            # File upload mode - redirect to upload handler
            return await test_voice_upload(audio, phone or "96176466674", provider or "montymobile")

        # Form data mode with voice_text (simulated transcription)
        if voice_text is None or voice_text.strip() == "":
            return {"success": False, "error": "Either audio file or voice_text is required"}

        request = TestVoiceRequest(
            phone=phone or "96176466674",
            voice_text=voice_text,
            provider=provider or "montymobile"
        )
        start_time = datetime.datetime.now()
        
        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print(f"=== VOICE TEST ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Voice text (simulated transcription): {request.voice_text}")
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {request.provider}: {str(e)}"}
        
        if request.provider == "qiscus":
            user_id = f"test_room_{request.phone}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[request.phone] = user_id
        else:
            user_id = request.phone
            
        user_name = f"Test User ({request.phone})"
        
        dashboard_bot_responses.pop(user_id, None)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }
        
        async def handle_voice_dashboard(user_whatsapp_id: str, voice_text: str, user_name: str):
            """Dashboard version for voice testing - simulates transcription"""
            if user_whatsapp_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_whatsapp_id] = {
                    'user_preferred_lang': 'ar', 
                    'initial_user_query_to_process': None, 
                    'awaiting_human_handover_confirmation': False, 
                    'current_conversation_id': None
                }

            # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
            # config.TESTING_MODE = True
            # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_whatsapp_id}")

            async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
                await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
                return True

            try:
                # Simulate voice message processing by directly calling text handler with transcribed text
                await handle_message(
                    user_id=user_whatsapp_id,
                    user_name=user_name,
                    user_input_text=voice_text,
                    user_data=config.user_data_whatsapp[user_whatsapp_id],
                    send_message_func=capture_send_message,
                    send_action_func=send_whatsapp_typing_indicator,
                    skip_firestore_save=True  # Skip saving since it's a test
                )
            except Exception as e:
                print(f"DEBUG: Error in handle_voice_dashboard: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"DEBUG: Processing voice message (text: '{request.voice_text}') for user {user_id}")
        
        try:
            await handle_voice_dashboard(user_id, request.voice_text, user_name)
            print(f"DEBUG: Voice message processing completed for user {user_id}")
        except Exception as e:
            print(f"DEBUG: Error in handle_voice_dashboard: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for any delayed processing tasks to complete (same as text messages)
        import asyncio
        if user_id in _delayed_processing_tasks:
            print(f"DEBUG: Waiting for delayed task for user {user_id} to complete...")
            try:
                await _delayed_processing_tasks[user_id]
                print(f"DEBUG: Delayed task completed for user {user_id}")
            except Exception as e:
                print(f"DEBUG: Delayed task error: {e}")
            finally:
                if user_id in _delayed_processing_tasks:
                    del _delayed_processing_tasks[user_id]
        else:
            print(f"DEBUG: No delayed task found for user {user_id}")
        
        captured_responses = dashboard_bot_responses.get(user_id, [])
        print(f"DEBUG: Captured responses for {user_id}: {captured_responses}")
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = "No response captured - check console for errors"
        
        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        dashboard_stats["conversations"].append({
            "user": user_name,
            "message": f"[Voice: {request.voice_text}]",
            "bot_response": bot_response,
            "timestamp": start_time.isoformat(),
            "provider": request.provider
        })
        
        return {
            "success": True,
            "message": "Test voice message processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "provider_info": {
                "provider": request.provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-voice-text")
async def test_voice_text(request: TestVoiceRequest):
    """Test voice message using JSON body with pre-transcribed text (simulates voice input)"""
    try:
        start_time = datetime.datetime.now()

        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print(f"=== VOICE TEXT TEST (JSON) ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Voice text: {request.voice_text}")
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {request.provider}: {str(e)}"}

        if request.provider == "qiscus":
            user_id = f"test_room_{request.phone}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[request.phone] = user_id
        else:
            user_id = request.phone

        user_name = f"Test User ({request.phone})"
        dashboard_bot_responses.pop(user_id, None)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }

        async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        await handle_message(
            user_id=user_id,
            user_name=user_name,
            user_input_text=request.voice_text,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=capture_send_message,
            send_action_func=send_whatsapp_typing_indicator,
            skip_firestore_save=True
        )

        # Wait for delayed tasks
        if user_id in _delayed_processing_tasks:
            try:
                await _delayed_processing_tasks[user_id]
            except Exception as e:
                print(f"DEBUG: Delayed task error: {e}")
            finally:
                if user_id in _delayed_processing_tasks:
                    del _delayed_processing_tasks[user_id]

        captured_responses = dashboard_bot_responses.get(user_id, [])
        bot_response = "\n\n".join(captured_responses) if captured_responses else "No response captured"

        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000

        return {
            "success": True,
            "message": "Voice text processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "transcription": request.voice_text,
            "provider_info": {
                "provider": request.provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-voice-upload")
async def test_voice_upload(
    audio: UploadFile = File(...),
    phone: str = Form("96176466674"),
    provider: str = Form("montymobile")
):
    """Test voice message processing with actual audio file upload"""
    try:
        start_time = datetime.datetime.now()
        
        print(f"=== VOICE UPLOAD TEST ===")
        print(f"Provider: {provider}")
        print(f"Phone: {phone}")
        print(f"Audio filename: {audio.filename}")
        print(f"Audio content type: {audio.content_type}")
        
        try:
            adapter = WhatsAppFactory.switch_provider(provider)
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {provider}: {str(e)}"}
        
        if provider == "qiscus":
            user_id = f"test_room_{phone}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[phone] = user_id
        else:
            user_id = phone
            
        user_name = f"Test User ({phone})"
        
        dashboard_bot_responses.pop(user_id, None)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }
        
        # Read audio file into BytesIO
        audio_bytes = await audio.read()
        print(f"DEBUG: Read {len(audio_bytes)} bytes from uploaded audio")
        audio_data_bytes = io.BytesIO(audio_bytes)
        audio_data_bytes.seek(0)
        
        # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
        # config.TESTING_MODE = True
        # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_id}")

        async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        try:
            # Process voice message (will transcribe and then handle as text)
            await handle_voice_message(
                user_id=user_id,
                user_name=user_name,
                audio_data_bytes=audio_data_bytes,
                user_data=config.user_data_whatsapp[user_id],
                send_message_func=capture_send_message,
                send_action_func=send_whatsapp_typing_indicator,
                audio_url=None  # No URL for test uploads
            )
        except Exception as e:
            print(f"DEBUG: Error in test_voice_upload: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for any delayed processing tasks to complete (voice -> text -> delayed processing)
        import asyncio
        if user_id in _delayed_processing_tasks:
            print(f"DEBUG: Waiting for delayed task for user {user_id} to complete...")
            try:
                await _delayed_processing_tasks[user_id]
                print(f"DEBUG: Delayed task completed for user {user_id}")
            except Exception as e:
                print(f"DEBUG: Delayed task error: {e}")
            finally:
                if user_id in _delayed_processing_tasks:
                    del _delayed_processing_tasks[user_id]
        else:
            print(f"DEBUG: No delayed task found for user {user_id}")
        
        captured_responses = dashboard_bot_responses.get(user_id, [])
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = "No response captured - check console for errors"
        
        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        dashboard_stats["conversations"].append({
            "user": user_name,
            "message": f"[Voice Upload: {audio.filename}]",
            "bot_response": bot_response,
            "timestamp": start_time.isoformat(),
            "provider": provider
        })
        
        return {
            "success": True,
            "message": "Test voice message processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "transcription": "Voice transcribed and processed",
            "provider_info": {
                "provider": provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }
        
    except Exception as e:
        print(f"ERROR in test_voice_upload: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/test-image-upload")
async def test_image_upload(
    image: UploadFile = File(...),
    phone: str = Form("96176466674"),
    provider: str = Form("montymobile")
):
    """Test image analysis through the bot with file upload"""
    try:
        start_time = datetime.datetime.now()
        
        print(f"=== IMAGE UPLOAD TEST ===")
        print(f"Provider: {provider}")
        print(f"Phone: {phone}")
        print(f"Image filename: {image.filename}")
        print(f"Image content type: {image.content_type}")
        
        try:
            adapter = WhatsAppFactory.switch_provider(provider)
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {provider}: {str(e)}"}
        
        if provider == "qiscus":
            user_id = f"test_room_{phone}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[phone] = user_id
        else:
            user_id = phone
            
        user_name = f"Test User ({phone})"
        
        dashboard_bot_responses.pop(user_id, None)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }
        
        # Read image file and convert to base64 data URL
        image_bytes = await image.read()
        print(f"DEBUG: Read {len(image_bytes)} bytes from uploaded image")
        
        # Detect image format from content type or filename
        content_type = image.content_type or "image/jpeg"
        if "png" in content_type.lower():
            image_format = "png"
        elif "gif" in content_type.lower():
            image_format = "gif"
        elif "webp" in content_type.lower():
            image_format = "webp"
        else:
            image_format = "jpeg"
        
        # Convert to base64 data URL
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/{image_format};base64,{base64_image}"
        print(f"DEBUG: Created base64 data URL with format: {image_format}")
        
        # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
        # config.TESTING_MODE = True
        # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_id}")

        async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        try:
            await handle_photo_message(
                user_id=user_id,
                user_name=user_name,
                image_url=image_url,
                user_data=config.user_data_whatsapp[user_id],
                send_message_func=capture_send_message,
                send_action_func=send_whatsapp_typing_indicator
            )
        finally:
            # config.TESTING_MODE = False
            # print(f"🧪 TESTING MODE DISABLED - Firebase saving re-enabled")
            pass

        captured_responses = dashboard_bot_responses.get(user_id, [])
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = "No response captured - check console for errors"
        
        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        dashboard_stats["conversations"].append({
            "user": user_name,
            "message": f"[Image Upload: {image.filename}]",
            "bot_response": bot_response,
            "timestamp": start_time.isoformat(),
            "provider": provider
        })
        
        return {
            "success": True,
            "message": "Test image processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "analysis": "Image analyzed successfully",
            "provider_info": {
                "provider": provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }
        
    except Exception as e:
        print(f"ERROR in test_image_upload: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    avg_response_time = 0
    if dashboard_stats["response_times"]:
        avg_response_time = sum(dashboard_stats["response_times"]) / len(dashboard_stats["response_times"])
    
    return {
        "total_messages": dashboard_stats["total_messages"],
        "active_users": len(dashboard_stats["active_users"]),
        "avg_response_time": f"{avg_response_time:.0f}ms",
        "current_provider": WhatsAppFactory.get_current_provider(),
        "recent_conversations": dashboard_stats["conversations"][-10:]
    }
