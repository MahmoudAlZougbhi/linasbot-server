"""Dashboard Testing Lab upload/stats leftovers (LOC split).

Lab HTTP handlers refuse with 403; bodies retained for reference until product cleanup.
"""

from __future__ import annotations

import base64
import datetime
import io
from typing import Any

from fastapi import File, Form, UploadFile

import config
from handlers.photo_handlers import handle_photo_message
from handlers.text_handlers import _delayed_processing_tasks
from handlers.voice_handlers import handle_voice_message
from modules.core import app, dashboard_stats
from modules.dashboard_api_helpers import (
    _await_dashboard_delayed_task,
    _dashboard_empty_capture_hint,
    _refuse_disabled_lab_endpoint,
    dashboard_captured_list_for_user,
    dashboard_clear_captured_for_user,
    dashboard_send_message_capture,
    restore_user_state_from_firestore,
)
from modules.whatsapp_adapters import send_whatsapp_typing_indicator
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory


@app.post("/api/test-voice-upload")
async def test_voice_upload(
    audio: UploadFile = File(...), phone: str = Form("96176466674"), provider: str = Form("meta")
) -> Any:
    """Test voice message processing with actual audio file upload"""
    _refuse_disabled_lab_endpoint()
    try:
        start_time = datetime.datetime.now()

        print("=== VOICE UPLOAD TEST ===")
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
            if hasattr(adapter, "room_mapping"):
                adapter.room_mapping[phone] = user_id
        else:
            user_id = phone

        user_name = f"Test User ({phone})"

        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
                "phone_number": phone,  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]["phone_number"] = phone

        # Restore user state from Firestore (for existing customers returning after server restart)
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        _dash_test_ud_vu = config.user_data_whatsapp[user_id]
        _dash_test_ud_vu["_dashboard_test_simulation"] = True
        try:
            # Read audio file into BytesIO
            audio_bytes = await audio.read()
            print(f"DEBUG: Read {len(audio_bytes)} bytes from uploaded audio")
            audio_data_bytes = io.BytesIO(audio_bytes)
            audio_data_bytes.seek(0)

            # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
            # config.TESTING_MODE = True
            # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_id}")

            async def capture_send_message(
                to_number: str,
                message_text: str | None = None,
                image_url: str | None = None,
                audio_url: str | None = None,
            ) -> Any:
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
                    audio_url=None,  # No URL for test uploads
                )
            except Exception as e:
                print(f"DEBUG: Error in test_voice_upload: {e}")
                import traceback

                traceback.print_exc()

            if user_id in _delayed_processing_tasks:
                await _await_dashboard_delayed_task(user_id)

            captured_responses = dashboard_captured_list_for_user(user_id)

            if captured_responses:
                bot_response = "\n\n".join(captured_responses)
            else:
                bot_response = _dashboard_empty_capture_hint(user_id)

            response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000

            dashboard_stats["total_messages"] += 1
            dashboard_stats["active_users"].add(user_id)
            dashboard_stats["response_times"].append(response_time)
            dashboard_stats["conversations"].append(
                {
                    "user": user_name,
                    "message": f"[Voice Upload: {audio.filename}]",
                    "bot_response": bot_response,
                    "timestamp": start_time.isoformat(),
                    "provider": provider,
                }
            )

            return {
                "success": True,
                "message": "Test voice message processed",
                "response_time_ms": response_time,
                "bot_response": bot_response,
                "transcription": "Voice transcribed and processed",
                "provider_info": {
                    "provider": provider,
                    "user_id_used": user_id,
                    "adapter_type": type(adapter).__name__,
                },
            }
        finally:
            _dash_test_ud_vu.pop("_dashboard_test_simulation", None)

    except Exception as e:
        print(f"ERROR in test_voice_upload: {e}")

        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/test-image-upload")
async def test_image_upload(
    image: UploadFile = File(...), phone: str = Form("96176466674"), provider: str = Form("meta")
) -> Any:
    """Test image analysis through the bot with file upload"""
    _refuse_disabled_lab_endpoint()
    try:
        start_time = datetime.datetime.now()

        print("=== IMAGE UPLOAD TEST ===")
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
            if hasattr(adapter, "room_mapping"):
                adapter.room_mapping[phone] = user_id
        else:
            user_id = phone

        user_name = f"Test User ({phone})"

        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
                "phone_number": phone,  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]["phone_number"] = phone

        # Restore user state from Firestore (for existing customers returning after server restart)
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

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

        async def capture_send_message(
            to_number: str, message_text: str | None = None, image_url: str | None = None, audio_url: str | None = None
        ) -> Any:
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        try:
            await handle_photo_message(
                user_id=user_id,
                user_name=user_name,
                image_url=image_url,
                user_data=config.user_data_whatsapp[user_id],
                send_message_func=capture_send_message,
                send_action_func=send_whatsapp_typing_indicator,
            )
        finally:
            # config.TESTING_MODE = False
            # print(f"🧪 TESTING MODE DISABLED - Firebase saving re-enabled")
            pass

        captured_responses = dashboard_captured_list_for_user(user_id)

        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = _dashboard_empty_capture_hint(user_id)

        response_time = (datetime.datetime.now() - start_time).total_seconds() * 1000

        dashboard_stats["total_messages"] += 1
        dashboard_stats["active_users"].add(user_id)
        dashboard_stats["response_times"].append(response_time)
        dashboard_stats["conversations"].append(
            {
                "user": user_name,
                "message": f"[Image Upload: {image.filename}]",
                "bot_response": bot_response,
                "timestamp": start_time.isoformat(),
                "provider": provider,
            }
        )

        return {
            "success": True,
            "message": "Test image processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "analysis": "Image analyzed successfully",
            "provider_info": {"provider": provider, "user_id_used": user_id, "adapter_type": type(adapter).__name__},
        }

    except Exception as e:
        print(f"ERROR in test_image_upload: {e}")

        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/stats")
async def get_stats() -> Any:
    """Get dashboard statistics"""
    avg_response_time = 0
    if dashboard_stats["response_times"]:
        avg_response_time = sum(dashboard_stats["response_times"]) / len(dashboard_stats["response_times"])

    return {
        "total_messages": dashboard_stats["total_messages"],
        "active_users": len(dashboard_stats["active_users"]),
        "avg_response_time": f"{avg_response_time:.0f}ms",
        "current_provider": WhatsAppFactory.get_current_provider(),
        "recent_conversations": dashboard_stats["conversations"][-10:],
    }
