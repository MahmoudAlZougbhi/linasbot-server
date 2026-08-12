"""WhatsApp photo inbound handler (LOC split)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

import config
from config import WHATSAPP_API_TOKEN
from handlers.text_handlers import _process_and_respond, handle_message
from handlers.training_handlers import handle_training_input
from modules.core import whatsapp_api_client
from modules.webhook_handlers_dedupe import await_whatsapp_delayed_processing
from services.api_integrations import log_report_event
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from utils.utils import save_conversation_message_to_firestore

async def _extract_image_base64_and_format(image_url: str, headers: dict[str, str] | None = None) -> tuple:
    """Extract base64 string and format from image_url (data: or http)."""
    import base64

    if image_url.startswith("data:image/"):
        parts = image_url.split(",", 1)
        if len(parts) != 2:
            raise ValueError("Invalid data URL format")
        mime_part = parts[0]
        base64_data = parts[1]
        fmt = mime_part.replace("data:image/", "").replace(";base64", "").strip()
        if fmt == "jpg":
            fmt = "jpeg"
        return base64_data, fmt or "jpeg"
    async with httpx.AsyncClient() as client:
        resp = await client.get(image_url, headers=headers or {}, timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        image_bytes = resp.content
    magic = image_bytes[:12] if len(image_bytes) >= 12 else image_bytes
    if magic[:3] == b"\xff\xd8\xff":
        fmt = "jpeg"
    elif magic[:4] == b"\x89PNG":
        fmt = "png"
    elif magic[:6] in (b"GIF87a", b"GIF89a"):
        fmt = "gif"
    elif len(magic) >= 12 and magic[:4] == b"RIFF" and magic[8:12] == b"WEBP":
        fmt = "webp"
    else:
        fmt = (
            "jpeg" if ("jpeg" in content_type or "jpg" in content_type) else "png" if "png" in content_type else "jpeg"
        )
    return base64.b64encode(image_bytes).decode("utf-8"), fmt


async def handle_photo_message_whatsapp_with_adapter(user_id: str, image_id: str, user_name: str, adapter: Any) -> Any:
    """Handle photo message: route image to main AI flow (no photo_analysis_service)."""
    try:
        current_provider = WhatsAppFactory.get_current_provider()

        print(f"DEBUG: Handling photo message - provider: {current_provider}, image_id: {image_id}")

        if current_provider == "qiscus":
            print("DEBUG: Using Qiscus provider - image_id is URL")
            image_url = image_id
        elif current_provider == "montymobile":
            print("DEBUG: Using MontyMobile provider - downloading media via MontyMobile API")

            # Use MontyMobile's media download endpoint
            # Based on their documentation: GET https://notification-qa.montylocal.net/api/v1/Push/external/{media_id}
            # Production endpoint should be similar pattern
            try:
                # MontyMobile media download endpoint (CORRECT - as provided by MontyMobile support)
                media_api_url = f"{adapter.base_url}/api/v2/WhatsappApi/get-media?MediaId={image_id}"

                montymobile_headers = {"Tenant": adapter.tenant_id, "api-key": adapter.api_token}

                print(f"DEBUG: Downloading media from MontyMobile API: {media_api_url}")
                print(f"DEBUG: Using Tenant: {adapter.tenant_id}")

                async with httpx.AsyncClient() as client:
                    # Download the media file directly
                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
                    media_response.raise_for_status()

                    # Detect image format from content-type header or magic bytes
                    content_type = media_response.headers.get("content-type", "").lower()
                    print(f"DEBUG: Media response content-type: {content_type}")
                    print(f"DEBUG: Media response size: {len(media_response.content)} bytes")

                    # Check if response is JSON (MontyMobile returns JSON with image data inside)
                    if "application/json" in content_type:
                        print("DEBUG: Response is JSON, extracting image data...")
                        media_json = media_response.json()
                        print(f"DEBUG: JSON keys: {list(media_json.keys())}")

                        # Extract the actual image data from JSON
                        # MontyMobile might return base64 data or a URL
                        if "data" in media_json:
                            image_data_field = media_json["data"]
                            if isinstance(image_data_field, str):
                                # It's base64 encoded
                                import base64

                                image_bytes = base64.b64decode(image_data_field)
                                print(f"DEBUG: Decoded base64 image from JSON, size: {len(image_bytes)} bytes")
                            elif isinstance(image_data_field, dict):
                                # It's a nested object, check for base64 or URL inside
                                print(f"DEBUG: data field is dict with keys: {list(image_data_field.keys())}")
                                # MontyMobile returns {"data": {"data": "base64string"}}
                                if "data" in image_data_field and isinstance(image_data_field["data"], str):
                                    # The actual base64 data is in data.data
                                    import base64

                                    image_bytes = base64.b64decode(image_data_field["data"])
                                    print(
                                        f"DEBUG: Decoded base64 image from nested data.data, size: {len(image_bytes)} bytes"
                                    )
                                elif (
                                    "base64" in image_data_field
                                    or "content" in image_data_field
                                    or "file" in image_data_field
                                ):
                                    # Try different possible field names
                                    base64_data = (
                                        image_data_field.get("base64")
                                        or image_data_field.get("content")
                                        or image_data_field.get("file")
                                    )
                                    if base64_data:
                                        import base64

                                        image_bytes = base64.b64decode(base64_data)
                                        print(
                                            f"DEBUG: Decoded base64 image from nested JSON, size: {len(image_bytes)} bytes"
                                        )
                                    else:
                                        print(
                                            f"DEBUG: Full data object: {json.dumps(image_data_field, indent=2)[:500]}..."
                                        )
                                        raise ValueError("Could not find base64 data in nested object")
                                elif "url" in image_data_field:
                                    image_url_from_json = image_data_field["url"]
                                    print(
                                        f"DEBUG: Found URL in nested data object, downloading from: {image_url_from_json}"
                                    )
                                    image_response = await client.get(image_url_from_json, timeout=30)
                                    image_response.raise_for_status()
                                    image_bytes = image_response.content
                                else:
                                    print(f"DEBUG: Full data object: {json.dumps(image_data_field, indent=2)}")
                                    raise ValueError("Could not find image data in nested object")
                            else:
                                print(f"DEBUG: Unexpected data format in JSON: {type(image_data_field)}")
                                raise ValueError("Unexpected image data format in JSON response")
                        elif "url" in media_json:
                            # It's a URL, download from there
                            image_url_from_json = media_json["url"]
                            print(f"DEBUG: Found URL in JSON, downloading from: {image_url_from_json}")
                            image_response = await client.get(image_url_from_json, timeout=30)
                            image_response.raise_for_status()
                            image_bytes = image_response.content
                        else:
                            print(f"DEBUG: Full JSON response: {json.dumps(media_json, indent=2)}")
                            raise ValueError("Could not find image data in JSON response")
                    else:
                        # Response is raw binary image
                        image_bytes = media_response.content
                        print("DEBUG: Response is raw binary image")

                    # Detect format from magic bytes (first few bytes of file)
                    magic_bytes = image_bytes[:8]
                    print(f"DEBUG: First 8 bytes (hex): {magic_bytes.hex()}")

                    # Determine image format
                    if magic_bytes.startswith(b"\xff\xd8\xff"):
                        image_format = "jpeg"
                    elif magic_bytes.startswith(b"\x89PNG"):
                        image_format = "png"
                    elif magic_bytes.startswith(b"GIF87a") or magic_bytes.startswith(b"GIF89a"):
                        image_format = "gif"
                    elif magic_bytes.startswith(b"RIFF") and magic_bytes[8:12] == b"WEBP":
                        image_format = "webp"
                    else:
                        # Fallback to content-type
                        if "jpeg" in content_type or "jpg" in content_type:
                            image_format = "jpeg"
                        elif "png" in content_type:
                            image_format = "png"
                        elif "gif" in content_type:
                            image_format = "gif"
                        elif "webp" in content_type:
                            image_format = "webp"
                        else:
                            image_format = "jpeg"  # Default fallback

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
            print("DEBUG: Using Meta/Facebook provider - fetching from Graph API")
            response = await whatsapp_api_client.get(
                f"/{image_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"}
            )
            response.raise_for_status()
            image_data = response.json()
            image_url = image_data.get("url")
            if not image_url:
                raise ValueError("Image URL not found in API response.")

        download_headers = (
            {"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"}
            if current_provider not in ("qiscus", "montymobile")
            else None
        )

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
            }

        user_data = config.user_data_whatsapp[user_id]
        base64_image, image_format = await _extract_image_base64_and_format(image_url, headers=download_headers)

        if config.user_in_training_mode.get(user_id, False):
            image_url_for_training = f"data:image/{image_format};base64,{base64_image}"

            async def adapter_send_message(
                to_number: str,
                message_text: str | None = None,
                image_url: str | None = None,
                audio_url: str | None = None,
            ) -> Any:
                if message_text:
                    return await adapter.send_text_message(to_number, message_text)
                elif image_url:
                    return await adapter.send_image_message(to_number, image_url)
                elif audio_url:
                    return await adapter.send_audio_message(to_number, audio_url)
                return False

            from modules.whatsapp_adapters import send_whatsapp_typing_indicator

            await handle_training_input(
                user_id=user_id,
                user_name=user_name,
                image_url=image_url_for_training,
                user_data=user_data,
                send_message_func=adapter_send_message,
                send_action_func=send_whatsapp_typing_indicator,
            )
            return

        source_message_id = user_data.pop("_source_message_id", None)
        image_metadata = {"type": "image"}
        if source_message_id:
            image_metadata["source_message_id"] = source_message_id
        from services.outbound_turn_idempotency import (
            record_inbound_mid_for_ai_turn,
            stable_ai_claim_identity,
            try_claim_ai_turn,
        )

        record_inbound_mid_for_ai_turn(user_data, source_message_id)
        await save_conversation_message_to_firestore(
            user_id,
            "user",
            "[صورة]",
            user_data.get("current_conversation_id"),
            user_name,
            user_data.get("phone_number"),
            metadata=image_metadata,
        )

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

        user_data["_ai_turn_trace_id"] = str(uuid.uuid4())
        trace = user_data["_ai_turn_trace_id"]
        user_data.pop("_batch_turn_body_fps", None)
        mids = user_data.pop("_batch_inbound_mids", []) or []
        claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
        if mids and not await try_claim_ai_turn(claim_id, mids):
            print(f"⚠️ [ai-turn] trace_id={trace} image claim=DUPLICATE_SKIP user={user_id[:20]}…")
            return
        if mids:
            print(f"[ai-turn] trace_id={trace} image claim=OK claim_key={claim_id[:20]}… mids_n={len(mids)}")
        else:
            print(
                f"[ai-turn] trace_id={trace} image claim=SKIPPED(no_inbound_mids) — "
                f"add TRACE or check provider message ids"
            )
        await _process_and_respond(
            user_id=user_id,
            user_name=user_name,
            user_input_to_process="[صورة]",
            user_data=user_data,
            send_message_func=adapter_send_message,
            send_action_func=send_whatsapp_typing_indicator,
            user_image_base64=base64_image,
            user_image_format=image_format,
        )

    except Exception as e:
        print(f"ERROR processing image {image_id} for user {user_id}: {e}")
        error_reply = "عذراً، واجهت مشكلة في معالجة صورتك. الرجاء المحاولة مرة أخرى."
        await adapter.send_text_message(user_id, error_reply)
        log_report_event(
            "whatsapp_media_download_failed",
            user_name,
            config.user_gender.get(user_id, "unspecified"),
            {"media_type": "image", "error": str(e)},
        )
        try:
            from services.interaction_flow_logger import is_flow_logging_enabled, log_interaction

            if is_flow_logging_enabled():
                log_interaction(
                    user_id,
                    "[صورة]",
                    error_reply,
                    "gpt",
                    user_name=user_name,
                    user_phone=config.user_data_whatsapp.get(user_id, {}).get("phone_number"),
                    user_gender=config.user_gender.get(user_id, "unknown"),
                    flow_steps=[
                        {
                            "step": 1,
                            "title": "Image received",
                            "content": "User sent image.",
                            "event_type": "image_received",
                            "status": "success",
                        },
                        {
                            "step": 2,
                            "title": "Image download/prepare failed",
                            "content": str(e),
                            "event_type": "error",
                            "status": "error",
                        },
                        {
                            "step": 3,
                            "title": "Bot → User (fallback)",
                            "content": error_reply,
                            "event_type": "fallback_triggered",
                        },
                    ],
                    flow_error=str(e),
                    message_type="image",
                )
        except Exception as log_err:
            print(f"⚠️ Could not log image error to Activity Flow: {log_err}")

