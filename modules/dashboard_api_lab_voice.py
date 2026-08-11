"""Dashboard Testing Lab voice leftovers (LOC split).

Lab HTTP handlers refuse with 403; bodies retained for reference until product cleanup.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import File, Form, UploadFile

import config
from handlers.text_handlers import _delayed_processing_tasks, handle_message
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
from modules.models import TestVoiceRequest
from modules.whatsapp_adapters import send_whatsapp_typing_indicator
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory


@app.post("/api/test-voice")
async def test_voice(
    audio: UploadFile = File(None), phone: str = Form(None), provider: str = Form(None), voice_text: str = Form(None)
) -> Any:
    """Test voice message processing - handles both file upload and text simulation"""
    _refuse_disabled_lab_endpoint()
    try:
        # Check if this is a file upload
        if audio is not None and audio.filename:
            # File upload mode - redirect to upload handler
            from modules.dashboard_api_lab_upload import test_voice_upload
            return await test_voice_upload(audio, phone or "96176466674", provider or "montymobile")

        # Form data mode with voice_text (simulated transcription)
        if voice_text is None or voice_text.strip() == "":
            return {"success": False, "error": "Either audio file or voice_text is required"}

        request = TestVoiceRequest(
            phone=phone or "96176466674", voice_text=voice_text, provider=provider or "montymobile"
        )
        start_time = datetime.datetime.now()

        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print("=== VOICE TEST ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Voice text (simulated transcription): {request.voice_text}")
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {request.provider}: {str(e)}"}

        if request.provider == "qiscus":
            user_id = f"test_room_{request.phone}"
            if hasattr(adapter, "room_mapping"):
                adapter.room_mapping[request.phone] = user_id
        else:
            user_id = request.phone

        user_name = f"Test User ({request.phone})"

        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
                "phone_number": request.phone,  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]["phone_number"] = request.phone

        # Restore user state from Firestore
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        _dash_test_ud_voice = config.user_data_whatsapp[user_id]
        _dash_test_ud_voice["_dashboard_test_simulation"] = True

        async def handle_voice_dashboard(user_whatsapp_id: str, voice_text: str, user_name: str) -> Any:
            """Dashboard version for voice testing - simulates transcription"""
            if user_whatsapp_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_whatsapp_id] = {
                    "user_preferred_lang": "ar",
                    "initial_user_query_to_process": None,
                    "awaiting_human_handover_confirmation": False,
                    "current_conversation_id": None,
                    "phone_number": request.phone,  # Store phone_number for Firestore saves
                }

            # NOTE: TESTING_MODE disabled - messages should be saved to Firebase
            # config.TESTING_MODE = True
            # print(f"🧪 TESTING MODE ENABLED - Firebase saving disabled for user {user_whatsapp_id}")

            async def capture_send_message(
                to_number: str,
                message_text: str | None = None,
                image_url: str | None = None,
                audio_url: str | None = None,
            ) -> Any:
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
                    skip_firestore_save=True,  # Skip saving since it's a test
                    message_combine_delay=0.0,
                )
            except Exception as e:
                print(f"DEBUG: Error in handle_voice_dashboard: {e}")
                import traceback

                traceback.print_exc()

        try:
            print(f"DEBUG: Processing voice message (text: '{request.voice_text}') for user {user_id}")

            try:
                await handle_voice_dashboard(user_id, request.voice_text, user_name)
                print(f"DEBUG: Voice message processing completed for user {user_id}")
            except Exception as e:
                print(f"DEBUG: Error in handle_voice_dashboard: {e}")

                import traceback

                traceback.print_exc()

            if user_id in _delayed_processing_tasks:
                await _await_dashboard_delayed_task(user_id)

            captured_responses = dashboard_captured_list_for_user(user_id)
            print(f"DEBUG: Captured responses for {user_id}: {captured_responses}")

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
                    "message": f"[Voice: {request.voice_text}]",
                    "bot_response": bot_response,
                    "timestamp": start_time.isoformat(),
                    "provider": request.provider,
                }
            )

            return {
                "success": True,
                "message": "Test voice message processed",
                "response_time_ms": response_time,
                "bot_response": bot_response,
                "provider_info": {
                    "provider": request.provider,
                    "user_id_used": user_id,
                    "adapter_type": type(adapter).__name__,
                },
            }
        finally:
            _dash_test_ud_voice.pop("_dashboard_test_simulation", None)

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-voice-text")
async def test_voice_text(request: TestVoiceRequest) -> Any:
    """Test voice message using JSON body with pre-transcribed text (simulates voice input)"""
    _refuse_disabled_lab_endpoint()
    try:
        start_time = datetime.datetime.now()

        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print("=== VOICE TEXT TEST (JSON) ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Voice text: {request.voice_text}")
        except Exception as e:
            return {"success": False, "error": f"Failed to switch to {request.provider}: {str(e)}"}

        if request.provider == "qiscus":
            user_id = f"test_room_{request.phone}"
            if hasattr(adapter, "room_mapping"):
                adapter.room_mapping[request.phone] = user_id
        else:
            user_id = request.phone

        user_name = f"Test User ({request.phone})"
        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
                "phone_number": request.phone,  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]["phone_number"] = request.phone

        # Restore user state from Firestore
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        _dash_test_ud_vt = config.user_data_whatsapp[user_id]
        _dash_test_ud_vt["_dashboard_test_simulation"] = True
        try:

            async def capture_send_message(
                to_number: str,
                message_text: str | None = None,
                image_url: str | None = None,
                audio_url: str | None = None,
            ) -> Any:
                await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
                return True

            await handle_message(
                user_id=user_id,
                user_name=user_name,
                user_input_text=request.voice_text,
                user_data=config.user_data_whatsapp[user_id],
                send_message_func=capture_send_message,
                send_action_func=send_whatsapp_typing_indicator,
                skip_firestore_save=True,
                message_combine_delay=0.0,
            )

            if user_id in _delayed_processing_tasks:
                await _await_dashboard_delayed_task(user_id)

            captured_responses = dashboard_captured_list_for_user(user_id)
            bot_response = (
                "\n\n".join(captured_responses) if captured_responses else _dashboard_empty_capture_hint(user_id)
            )

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
                    "adapter_type": type(adapter).__name__,
                },
            }
        finally:
            _dash_test_ud_vt.pop("_dashboard_test_simulation", None)

    except Exception as e:
        return {"success": False, "error": str(e)}
