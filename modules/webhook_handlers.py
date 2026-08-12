"""
Webhook handlers module: Message parsing and processing
Handles webhook reception, parsing, and routing messages to appropriate handlers.
"""

from __future__ import annotations

import hmac
import os
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import config
from config import TRAINER_WHATSAPP_NUMBER
from handlers.text_handlers import handle_message
from handlers.training_handlers import exit_training_mode, start_training_mode
from modules.core import app
from modules.webhook_handlers_dedupe import (  # noqa: F401
    _PROCESS_PARSED_MID_TTL_SECONDS,
    WEBHOOK_DEDUP_WINDOW_SECONDS,
    WEBHOOK_TEXT_BODYFP_MAX_CHARS,
    WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS,
    _extract_text_from_content,
    _process_parsed_mid_claims,
    _process_parsed_mid_locks,
    _process_parsed_release_claim_on_error,
    _process_parsed_should_skip_duplicate,
    _synthetic_inbound_id_from_wa_message,
    _webhook_bodyfp_cache,
    _webhook_bodyfp_firestore_try_acquire,
    _webhook_bodyfp_locks,
    _webhook_bodyfp_try_claim,
    _webhook_dedup_cache,
    _webhook_firestore_try_acquire,
    _webhook_memory_dedup_locks,
    _webhook_memory_try_claim,
    _webhook_text_body_fingerprint,
    await_whatsapp_delayed_processing,
)
from modules.webhook_handlers_parse import (  # noqa: F401
    _count_images_in_single_message,
    _count_non_empty_lines,
    _is_image_attachment,
    _parse_webhook_raw_dict,
    _webhook_is_meta_status_only,
    extract_meta_message_content,
    handle_meta_webhook,
)
from modules.webhook_handlers_photo import handle_photo_message_whatsapp_with_adapter  # noqa: F401
from modules.webhook_handlers_process import (  # noqa: F401
    _process_parsed_message_impl,
    process_parsed_message,
    start_command_whatsapp,
)
from modules.webhook_handlers_voice import handle_voice_message_whatsapp_with_adapter  # noqa: F401
from services.api_integrations import generate_daily_report_command
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

# Debug: last webhook received/parsed (for /api/debug/webhook-status)
_last_webhook_received_at = None
_last_webhook_parsed_at = None
_last_webhook_user_id = None


def get_webhook_debug_status() -> Any:
    """Return last webhook timestamps for /api/debug/webhook-status."""
    import datetime

    return {
        "last_received_at": _last_webhook_received_at,
        "last_received_iso": datetime.datetime.fromtimestamp(_last_webhook_received_at).isoformat()
        if _last_webhook_received_at
        else None,
        "last_parsed_at": _last_webhook_parsed_at,
        "last_parsed_user_id": _last_webhook_user_id,
        "seconds_since_received": round(time.time() - _last_webhook_received_at, 1)
        if _last_webhook_received_at
        else None,
    }


@app.get("/webhook")
async def verify_webhook(request: Request) -> Any:
    """Endpoint for WhatsApp webhook verification."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    if not VERIFY_TOKEN or VERIFY_TOKEN == "YOUR_SECURE_VERIFY_TOKEN":
        raise HTTPException(status_code=500, detail="WHATSAPP_WEBHOOK_VERIFY_TOKEN must be set in .env")

    if mode == "subscribe" and token is not None and hmac.compare_digest(token, VERIFY_TOKEN):
        print("WEBHOOK_VERIFIED")
        if challenge is None or (isinstance(challenge, str) and not challenge.strip()):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge")
        try:
            return int(challenge)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail="Invalid webhook challenge format") from e
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request) -> Any:
    """Endpoint for receiving WhatsApp messages from different providers.

    Inbound WhatsApp (MontyMobile / Meta Cloud / any provider) must not invoke the AI.
    Facebook Messenger and Instagram DMs are handled only on /webhook/meta-messaging.
    WhatsApp numbers remain available as social-channel handoff destinations only.

    Authentication: require Meta X-Hub-Signature-256 when WHATSAPP_APP_SECRET is set,
    otherwise require X-Webhook-Secret == WHATSAPP_WEBHOOK_INGEST_SECRET.
    In production, one of these secrets must be configured.
    """
    global _last_webhook_received_at, _last_webhook_parsed_at, _last_webhook_user_id
    try:
        raw_body = await request.body()
        app_secret = (os.getenv("WHATSAPP_APP_SECRET") or os.getenv("META_APP_SECRET") or "").strip()
        ingest_secret = (os.getenv("WHATSAPP_WEBHOOK_INGEST_SECRET") or "").strip()
        env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
        is_prod = env in {"prod", "production"}

        authenticated = False
        if app_secret:
            from services.meta_messaging import verify_meta_signature

            if verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), app_secret):
                authenticated = True
            else:
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
        elif ingest_secret:
            provided = (request.headers.get("X-Webhook-Secret") or "").strip()
            if not provided or not hmac.compare_digest(provided, ingest_secret):
                raise HTTPException(status_code=401, detail="Invalid webhook secret")
            authenticated = True
        elif is_prod:
            raise HTTPException(
                status_code=503,
                detail="WhatsApp webhook authentication is not configured",
            )
        else:
            # Local/dev without secrets: accept but do not run AI
            authenticated = True

        _last_webhook_received_at = time.time()
        print(
            f"📥 WhatsApp webhook POST received ({len(raw_body)} bytes) auth={authenticated} — "
            "inbound AI disabled (social handoff-only policy)"
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ignored",
                "reason": "whatsapp_inbound_ai_disabled",
                "accepted": 0,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"CRITICAL ERROR acknowledging WhatsApp webhook: {e}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "ignored",
                "reason": "whatsapp_inbound_ai_disabled",
                "accepted": 0,
            },
        )



async def handle_message_whatsapp_with_adapter(
    user_id: str, user_input_text: str, user_name: str, adapter: Any, phone_number: str | None = None
) -> Any:
    """Handle message with specific adapter"""
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            "user_preferred_lang": "ar",
            "initial_user_query_to_process": None,
            "awaiting_human_handover_confirmation": False,
            "current_conversation_id": None,
        }

    if phone_number:
        config.user_data_whatsapp[user_id]["phone_number"] = phone_number
        print(f"✅ DEBUG: Stored phone_number ***{str(phone_number)[-4:]} for user ...{str(user_id)[-4:]}")
    else:
        print(f"❌ CRITICAL: No phone_number extracted for user ...{str(user_id)[-4:]}!")
        config.user_data_whatsapp[user_id]["phone_number"] = None

    _same_turn_text_sends = set()

    async def adapter_send_message(
        to_number: str, message_text: str | None = None, image_url: str | None = None, audio_url: str | None = None
    ) -> Any:
        if message_text:
            from services.whatsapp_adapters.outbound_text_dedupe import outbound_fingerprint

            fp = outbound_fingerprint(
                to_number,
                message_text,
                phone_hint=phone_number or config.user_data_whatsapp.get(user_id, {}).get("phone_number"),
            )
            if fp and fp in _same_turn_text_sends:
                tid = config.user_data_whatsapp.get(user_id, {}).get("_ai_turn_trace_id", "?")
                print(
                    f"⚠️ [whatsapp-send] trace_id={tid} dedupe=same_turn_suppressed "
                    f"user={user_id[:16]}… text_len={len(message_text)}"
                )
                return {"success": True, "deduped_same_turn": True}
            result = await adapter.send_text_message(to_number, message_text)
            tid = config.user_data_whatsapp.get(user_id, {}).get("_ai_turn_trace_id", "?")
            if result:
                if result.get("deduped_outbound"):
                    print(
                        f"[whatsapp-send] trace_id={tid} dedupe=global_window user={user_id[:12]}… "
                        f"text_len={len(message_text)}"
                    )
                elif (
                    result.get("success")
                    and not result.get("dry_run")
                    and os.getenv("TRACE_AI_OUTBOUND", "").lower() in ("1", "true", "yes")
                ):
                    print(f"[whatsapp-send] trace_id={tid} sent=ok user=...{str(user_id)[-4:]} text_len={len(message_text)}")
            if fp and result and result.get("success"):
                _same_turn_text_sends.add(fp)
            return result
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
        send_action_func=send_whatsapp_typing_indicator,
    )
    await await_whatsapp_delayed_processing(user_id)



async def start_training_mode_whatsapp(user_whatsapp_id: str) -> Any:
    """Adapts start_training_mode for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str | None = None, img: str | None = None, aud: str | None = None) -> Any:
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        if user_whatsapp_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_whatsapp_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
            }

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator

        await start_training_mode(
            user_id=user_whatsapp_id,
            user_data=config.user_data_whatsapp[user_whatsapp_id],
            send_message_func=_adapter_send,
            send_action_func=send_whatsapp_typing_indicator,
        )
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لتفعيل وضع التدريب.")


async def exit_training_mode_whatsapp(user_whatsapp_id: str) -> Any:
    """Adapts exit_training_mode for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str | None = None, img: str | None = None, aud: str | None = None) -> Any:
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        if user_whatsapp_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_whatsapp_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
            }

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator

        await exit_training_mode(
            user_id=user_whatsapp_id,
            user_data=config.user_data_whatsapp[user_whatsapp_id],
            send_message_func=_adapter_send,
            send_action_func=send_whatsapp_typing_indicator,
        )
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لإلغاء تفعيل وضع التدريب.")


async def generate_daily_report_command_whatsapp(user_whatsapp_id: str) -> Any:
    """Adapts generate_daily_report_command for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str | None = None, img: str | None = None, aud: str | None = None) -> Any:
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
            await generate_daily_report_command(user_id=user_whatsapp_id, send_message_func=_adapter_send)
        except Exception as e:
            print(f"ERROR generating daily report for {user_whatsapp_id}: {e}")
            await adapter.send_text_message(user_whatsapp_id, f"حدث خطأ أثناء توليد التقرير: {str(e)}")
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لطلب التقرير اليومي.")


async def send_whatsapp_typing_indicator(user_whatsapp_id: str) -> None:
    """Sends a typing indicator to WhatsApp."""
    print(f"DEBUG: WhatsApp typing indicator for {user_whatsapp_id} (simulated).\n")
