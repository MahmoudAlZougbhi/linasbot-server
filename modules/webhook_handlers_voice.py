"""WhatsApp voice inbound handler (LOC split)."""

from __future__ import annotations

import io
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
    """Handle voice message with Meta Cloud media download only."""
    try:
        current_provider = WhatsAppFactory.get_current_provider()
        print(f"DEBUG: Handling audio message - provider: {current_provider}, audio_id: {audio_id}")

        if current_provider not in ("meta", "cloud"):
            raise ValueError(
                f"WhatsApp media download refused for provider {current_provider!r}; "
                "Meta Cloud is the only supported runtime transport."
            )

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
            audio_content_response = await client.get(
                audio_url, headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"}, timeout=30
            )
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

        await handle_voice_message(
            user_id=user_id,
            user_name=user_name,
            audio_data_bytes=audio_data_bytes,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=adapter_send_message,
            send_action_func=send_whatsapp_typing_indicator,
            audio_url=audio_url,
        )
        await await_whatsapp_delayed_processing(user_id)

    except Exception as e:
        print(f"ERROR processing audio {audio_id} for user ...{str(user_id)[-4:]}: {e}")
        await adapter.send_text_message(
            user_id, "عذراً، واجهت مشكلة في معالجة رسالتك الصوتية. الرجاء المحاولة مرة أخرى."
        )
        log_report_event(
            "whatsapp_media_download_failed",
            user_name,
            config.user_gender.get(user_id, "unspecified"),
            {"media_type": "audio", "error": str(e)},
        )
