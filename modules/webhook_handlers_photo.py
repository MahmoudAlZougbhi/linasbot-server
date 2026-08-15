"""WhatsApp photo inbound handler (LOC split)."""

from __future__ import annotations

# unused import removed from photo handler path
import uuid
from typing import Any

import httpx

import config
from config import WHATSAPP_API_TOKEN
from handlers.text_handlers import _process_and_respond
from handlers.training_handlers import handle_training_input
from modules.core import whatsapp_api_client
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
    """Handle photo message: route image to main AI flow (Meta Cloud media only)."""
    try:
        current_provider = WhatsAppFactory.get_current_provider()
        print(f"DEBUG: Handling photo message - provider: {current_provider}, image_id: {image_id}")

        if current_provider not in ("meta", "cloud"):
            raise ValueError(
                f"WhatsApp media download refused for provider {current_provider!r}; "
                "Meta Cloud is the only supported runtime transport."
            )

        print("DEBUG: Using Meta/Facebook provider - fetching from Graph API")
        response = await whatsapp_api_client.get(
            f"/{image_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"}
        )
        response.raise_for_status()
        image_data = response.json()
        image_url = image_data.get("url")
        if not image_url:
            raise ValueError("Image URL not found in API response.")

        download_headers = {"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"}

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
        if mids and not await try_claim_ai_turn(
            claim_id,
            mids,
            binding_id=str(user_data.get("meta_binding_id") or ""),
            inbound_event_id=str(user_data.get("_inbound_event_id") or ""),
        ):
            print(f"⚠️ [ai-turn] trace_id={trace} image claim=DUPLICATE_SKIP user=...{str(user_id)[-4:]}")
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
        print(f"ERROR processing image {image_id} for user ...{str(user_id)[-4:]}: {e}")
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
