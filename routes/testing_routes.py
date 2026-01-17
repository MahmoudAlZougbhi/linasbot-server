# -*- coding: utf-8 -*-
"""
Testing and Dashboard API Routes
"""
from fastapi import APIRouter, File, UploadFile, Form
from pydantic import BaseModel
import datetime
import asyncio
import io
import os
import base64
import tempfile
import config
from handlers.text_handlers import handle_message, _process_and_respond
from handlers.photo_handlers import handle_photo_message
from handlers.voice_handlers import handle_voice_message
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from services.llm_core_service import client as openai_client
from utils.utils import detect_language

# Try to import pydub for audio processing
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None

router = APIRouter()

# Pydantic models
class TestMessageRequest(BaseModel):
    phone: str
    message: str
    provider: str = "meta"

class TestImageRequest(BaseModel):
    phone: str
    image_url: str
    caption: str = ""
    provider: str = "meta"

class ProviderSwitchRequest(BaseModel):
    provider: str

class TestVoiceRequest(BaseModel):
    phone: str
    voice_text: str
    provider: str = "meta"

# Dashboard Statistics
dashboard_stats = {
    "total_messages": 0,
    "active_users": set(),
    "response_times": [],
    "conversations": []
}

# Global variable to capture bot responses for dashboard
dashboard_bot_responses = {}

async def dashboard_send_message_capture(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
    """Capture bot responses for dashboard display"""
    if message_text:
        if to_number not in dashboard_bot_responses:
            dashboard_bot_responses[to_number] = []
        dashboard_bot_responses[to_number].append(message_text)
        print(f"Dashboard captured bot response for {to_number}: {message_text}")
    return True

async def send_whatsapp_typing_indicator(user_whatsapp_id: str):
    """Sends a typing indicator (simulated for testing)"""
    print(f"DEBUG: WhatsApp typing indicator for {user_whatsapp_id} (simulated).\n")

@router.get("/api/test")
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
            "Q&A Management",
            "Live Chat Monitoring"
        ],
        "current_provider": WhatsAppFactory.get_current_provider(),
        "timestamp": datetime.datetime.now().isoformat()
    }

@router.post("/api/test-firebase")
async def test_firebase():
    """Test Firebase Firestore connection"""
    try:
        from utils.utils import get_firestore_db, save_conversation_message_to_firestore, update_dashboard_metric_in_firestore
        
        db = get_firestore_db()
        if not db:
            return {
                "success": False,
                "error": "Firestore not initialized",
                "details": "Firebase connection failed"
            }
        
        test_user_id = "test_firebase_user"
        test_message = f"Firebase test message at {datetime.datetime.now().isoformat()}"
        
        print(f"🧪 Testing Firebase with user: {test_user_id}")
        
        await save_conversation_message_to_firestore(
            user_id=test_user_id,
            role="user",
            text="Hello, this is a test message from user",
            conversation_id=None
        )
        
        if test_user_id in config.user_data_whatsapp:
            conversation_id = config.user_data_whatsapp[test_user_id].get('current_conversation_id')
            if conversation_id:
                await save_conversation_message_to_firestore(
                    user_id=test_user_id,
                    role="ai",
                    text="Hello! This is a test response from the bot",
                    conversation_id=conversation_id
                )
        
        app_id_for_firestore = "linas-ai-bot-backend"
        conversations_collection = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(test_user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
        
        conversations = []
        docs = conversations_collection.stream()
        for doc in docs:
            doc_data = doc.to_dict()
            conversations.append({
                "id": doc.id,
                "messages": doc_data.get("messages", []),
                "timestamp": doc_data.get("timestamp"),
                "user_id": doc_data.get("user_id")
            })
        
        await update_dashboard_metric_in_firestore(test_user_id, "test_messages", 1)
        
        return {
            "success": True,
            "message": "Firebase test completed successfully!",
            "results": {
                "firestore_connected": True,
                "conversations_saved": len(conversations),
                "test_user_id": test_user_id,
                "conversations": conversations,
                "metrics_updated": True
            },
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"❌ Firebase test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "details": "Check console for full error details"
        }

@router.post("/api/switch-provider")
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

@router.post("/api/test-message")
async def test_message(request: TestMessageRequest):
    """Send a test message through the bot"""
    try:
        start_time = datetime.datetime.now()
        
        adapter = WhatsAppFactory.switch_provider(request.provider)
        
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

        async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            if request.provider == "qiscus":
                try:
                    result = await adapter.send_text_message(to_number, message_text)
                except Exception as e:
                    print(f"DEBUG: Qiscus send failed (expected in test): {e}")
            return True

        try:
            await handle_message(
                user_id=user_id,
                user_name=user_name,
                user_input_text=request.message,
                user_data=config.user_data_whatsapp[user_id],
                send_message_func=capture_send_message,
                send_action_func=send_whatsapp_typing_indicator
            )
        finally:
            # config.TESTING_MODE = False
            pass
        
        captured_responses = dashboard_bot_responses.get(user_id, [])
        bot_response = "\n\n".join(captured_responses) if captured_responses else "No response captured"
        
        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        
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

@router.post("/api/test-voice")
async def test_voice_message(
    audio: UploadFile = File(None),
    phone: str = Form(None),
    provider: str = Form(None),
    timestamp: str = Form(None),
):
    """
    Test voice message through the bot.
    Accepts either:
    - FormData with audio file upload
    - JSON with voice_text (simulates transcribed voice)
    """
    try:
        start_time = datetime.datetime.now()

        # Handle JSON body request (voice_text simulation)
        # FastAPI will try FormData first, if that fails we need to parse JSON
        # For now, check if audio file was provided

        transcribed_text = None
        audio_duration = None

        if audio and audio.filename:
            # File upload case - transcribe with Whisper
            if not PYDUB_AVAILABLE:
                return {"success": False, "error": "Audio processing not available (pydub not installed)"}

            # Read audio file
            audio_content = await audio.read()
            audio_bytes = io.BytesIO(audio_content)

            try:
                # Convert to MP3 for Whisper
                audio_segment = AudioSegment.from_file(audio_bytes, format="ogg")
                audio_duration = len(audio_segment) / 1000.0  # Duration in seconds

                mp3_buffer = io.BytesIO()
                audio_segment.export(mp3_buffer, format="mp3")
                mp3_buffer.seek(0)
                mp3_buffer.name = "voice_message.mp3"

                # Transcribe with Whisper
                transcription_response = await openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=mp3_buffer,
                    language="ar"
                )
                transcribed_text = transcription_response.text
                print(f"🎤 Voice transcription: {transcribed_text}")

            except Exception as e:
                return {"success": False, "error": f"Audio transcription failed: {str(e)}"}
        else:
            return {"success": False, "error": "No audio file provided"}

        # Set up user and provider
        phone_number = phone or "123456789"
        selected_provider = provider or "meta"

        adapter = WhatsAppFactory.switch_provider(selected_provider)

        if selected_provider == "qiscus":
            user_id = f"test_room_{phone_number}"
            if hasattr(adapter, 'room_mapping'):
                adapter.room_mapping[phone_number] = user_id
        else:
            user_id = phone_number

        user_name = f"Test User ({phone_number})"
        dashboard_bot_responses.pop(user_id, None)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None
            }

        # Create capture function for responses
        async def capture_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        # Process the transcribed text through the message handler
        await handle_message(
            user_id=user_id,
            user_name=user_name,
            user_input_text=transcribed_text,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=capture_send_message,
            send_action_func=send_whatsapp_typing_indicator
        )

        # Collect captured responses
        captured_responses = dashboard_bot_responses.get(user_id, [])
        bot_response = "\n\n".join(captured_responses) if captured_responses else "No response captured"

        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000

        # Update stats
        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)

        return {
            "success": True,
            "message": "Voice message processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "transcription": transcribed_text,
            "duration": audio_duration,
            "provider_info": {
                "provider": selected_provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@router.post("/api/test-voice-text")
async def test_voice_text(request: TestVoiceRequest):
    """
    Test voice message using pre-transcribed text (simulates voice input).
    This is useful for testing without actual audio files.
    """
    try:
        start_time = datetime.datetime.now()

        adapter = WhatsAppFactory.switch_provider(request.provider)

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

        # Process the voice text through the message handler
        await handle_message(
            user_id=user_id,
            user_name=user_name,
            user_input_text=request.voice_text,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=capture_send_message,
            send_action_func=send_whatsapp_typing_indicator
        )

        captured_responses = dashboard_bot_responses.get(user_id, [])
        bot_response = "\n\n".join(captured_responses) if captured_responses else "No response captured"

        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000

        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)

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

@router.get("/api/stats")
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
