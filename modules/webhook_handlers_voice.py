"""WhatsApp voice inbound handler (LOC split)."""

from __future__ import annotations

import io
import json
from typing import Any

import httpx

import config
from config import WHATSAPP_API_TOKEN
from handlers.voice_handlers import handle_voice_message
from modules.core import whatsapp_api_client
from modules.webhook_handlers_dedupe import await_whatsapp_delayed_processing
from services.api_integrations import log_report_event
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

async def handle_voice_message_whatsapp_with_adapter(user_id: str, audio_id: str, user_name: str, adapter: Any) -> Any:
    """Handle voice message with specific adapter"""
    try:
        current_provider = WhatsAppFactory.get_current_provider()

        print(f"DEBUG: Handling audio message - provider: {current_provider}, audio_id: {audio_id}")

        # Extract audio URL based on provider
        audio_url = None
        if current_provider == "qiscus":
            # For Qiscus, audio_id IS the full URL
            print("DEBUG: Using Qiscus provider - audio_id is URL")
            audio_url = audio_id
            async with httpx.AsyncClient() as client:
                audio_content_response = await client.get(audio_id)
                audio_content_response.raise_for_status()
                audio_data_bytes = io.BytesIO(audio_content_response.content)
                audio_data_bytes.seek(0)
        elif current_provider == "montymobile":
            print("DEBUG: Using MontyMobile provider - downloading audio via MontyMobile API")

            try:
                # MontyMobile media download endpoint (same as images)
                media_api_url = f"{adapter.base_url}/api/v2/WhatsappApi/get-media?MediaId={audio_id}"

                montymobile_headers = {"Tenant": adapter.tenant_id, "api-key": adapter.api_token}

                print(f"DEBUG: Downloading audio from MontyMobile API: {media_api_url}")
                print(f"DEBUG: Using Tenant: {adapter.tenant_id}")

                async with httpx.AsyncClient() as client:
                    # Download the media file
                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
                    media_response.raise_for_status()

                    content_type = media_response.headers.get("content-type", "").lower()
                    print(f"DEBUG: Audio response content-type: {content_type}")
                    print(f"DEBUG: Audio response size: {len(media_response.content)} bytes")

                    # Check if response is JSON (MontyMobile returns JSON with audio data inside)
                    if "application/json" in content_type:
                        print("DEBUG: Response is JSON, extracting audio data...")
                        media_json = media_response.json()
                        print(f"DEBUG: JSON keys: {list(media_json.keys())}")

                        # Extract the actual audio data from JSON (same structure as images)
                        if "data" in media_json:
                            audio_data_field = media_json["data"]
                            if isinstance(audio_data_field, str):
                                # It's base64 encoded
                                import base64

                                audio_bytes = base64.b64decode(audio_data_field)
                                print(f"DEBUG: Decoded base64 audio from JSON, size: {len(audio_bytes)} bytes")
                            elif isinstance(audio_data_field, dict):
                                # It's a nested object
                                print(f"DEBUG: data field is dict with keys: {list(audio_data_field.keys())}")
                                # MontyMobile returns {"data": {"data": "base64string"}}
                                if "data" in audio_data_field and isinstance(audio_data_field["data"], str):
                                    # The actual base64 data is in data.data
                                    import base64

                                    audio_bytes = base64.b64decode(audio_data_field["data"])
                                    print(
                                        f"DEBUG: Decoded base64 audio from nested data.data, size: {len(audio_bytes)} bytes"
                                    )
                                elif "url" in audio_data_field:
                                    audio_url_from_json = audio_data_field["url"]
                                    print(
                                        f"DEBUG: Found URL in nested data object, downloading from: {audio_url_from_json}"
                                    )
                                    audio_response = await client.get(audio_url_from_json, timeout=30)
                                    audio_response.raise_for_status()
                                    audio_bytes = audio_response.content
                                else:
                                    print(f"DEBUG: Full data object: {json.dumps(audio_data_field, indent=2)[:500]}...")
                                    raise ValueError("Could not find audio data in nested object")
                            else:
                                print(f"DEBUG: Unexpected data format in JSON: {type(audio_data_field)}")
                                raise ValueError("Unexpected audio data format in JSON response")
                        elif "url" in media_json:
                            # It's a URL, download from there
                            audio_url_from_json = media_json["url"]
                            print(f"DEBUG: Found URL in JSON, downloading from: {audio_url_from_json}")
                            audio_response = await client.get(audio_url_from_json, timeout=30)
                            audio_response.raise_for_status()
                            audio_bytes = audio_response.content
                        else:
                            print(f"DEBUG: Full JSON response: {json.dumps(media_json, indent=2)[:500]}...")
                            raise ValueError("Could not find audio data in JSON response")
                    else:
                        # Response is raw binary audio
                        audio_bytes = media_response.content
                        print("DEBUG: Response is raw binary audio")

                    # Create BytesIO object for audio processing
                    audio_data_bytes = io.BytesIO(audio_bytes)
                    audio_data_bytes.seek(0)
                    print("DEBUG: Created BytesIO object for audio processing")

                    # Upload audio to Firebase Storage to get a playable URL for the dashboard
                    try:
                        import base64

                        from utils.utils import upload_base64_to_firebase_storage

                        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
                        file_name = f"voice_{user_id}_{audio_id[:8]}.ogg"

                        audio_url = await upload_base64_to_firebase_storage(
                            audio_base64, file_name, file_type="audio/ogg"
                        )

                        if audio_url:
                            print(f"DEBUG: Uploaded audio to Firebase Storage: {audio_url}")
                        else:
                            print("DEBUG: Failed to upload audio to Firebase Storage, audio_url will be None")
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
            print("DEBUG: Using Meta/Facebook provider - fetching from Graph API")
            response = await whatsapp_api_client.get(
                f"/{audio_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"}
            )
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
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
            }

        async def adapter_send_message(
            to_number: str, message_text: str | None = None, image_url: str | None = None, audio_url: str | None = None
        ) -> Any:
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
            audio_url=audio_url,  # ✅ NEW: Pass the URL so voice message has type="voice" + audio_url in Firebase
        )
        await await_whatsapp_delayed_processing(user_id)

    except Exception as e:
        print(f"ERROR processing audio {audio_id} for user {user_id}: {e}")
        await adapter.send_text_message(
            user_id, "عذراً، واجهت مشكلة في معالجة رسالتك الصوتية. الرجاء المحاولة مرة أخرى."
        )
        log_report_event(
            "whatsapp_media_download_failed",
            user_name,
            config.user_gender.get(user_id, "unspecified"),
            {"media_type": "audio", "error": str(e)},
        )

