# -*- coding: utf-8 -*-
"""
Dashboard API module: Testing and simulation endpoints
Provides endpoints for dashboard testing of the bot functionality.
"""

import asyncio
import datetime
import base64
import tempfile
import os
import io
import json
import re
from typing import Dict, Any, List, Optional

from fastapi import File, UploadFile, Form, Request
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


async def restore_user_state_from_firestore(user_id: str) -> str:
    """
    Restore user state (gender, name, greeting_stage) from Firestore.
    Returns the restored name if found, otherwise returns None.
    This is needed for dashboard test endpoints which bypass webhook_handlers.
    """
    current_gender = config.user_gender.get(user_id)
    restored_name = None

    if current_gender not in ["male", "female"]:
        try:
            from utils.utils import get_user_state_from_firestore
            print(f"🔄 [Dashboard] Restoring user state from Firestore for {user_id}...")
            firestore_state = await get_user_state_from_firestore(user_id)

            if firestore_state:
                # Restore gender
                firestore_gender = firestore_state.get("gender", "")
                if firestore_gender in ["male", "female"]:
                    config.user_gender[user_id] = firestore_gender
                    print(f"✅ [Dashboard] Restored gender from Firestore: {firestore_gender}")

                # Restore greeting stage
                firestore_greeting_stage = firestore_state.get("greeting_stage", 0)
                if firestore_greeting_stage > 0:
                    config.user_greeting_stage[user_id] = firestore_greeting_stage
                    print(f"✅ [Dashboard] Restored greeting_stage from Firestore: {firestore_greeting_stage}")

                # Restore name
                firestore_name = firestore_state.get("name", "")
                if firestore_name and firestore_name != "Unknown Customer":
                    config.user_names[user_id] = firestore_name
                    restored_name = firestore_name
                    print(f"✅ [Dashboard] Restored name from Firestore: {firestore_name}")
            else:
                print(f"ℹ️ [Dashboard] No user state found in Firestore for {user_id}")
        except Exception as e:
            print(f"❌ [Dashboard] Error restoring user state: {e}")
            import traceback
            traceback.print_exc()

    return restored_name


async def dashboard_send_message_capture(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
    """Capture bot responses for dashboard display"""
    line = None
    if message_text and str(message_text).strip():
        line = str(message_text).strip()
    elif image_url:
        line = "[Image reply — no text body; check provider / server logs]"
    elif audio_url:
        line = "[Voice/audio reply — no text body; check provider / server logs]"
    if line:
        for key in _whatsapp_id_variants(to_number):
            if key not in dashboard_bot_responses:
                dashboard_bot_responses[key] = []
            dashboard_bot_responses[key].append(line)
        print(f"Dashboard captured bot response for {to_number}: {line[:500]}")
    return True


def _whatsapp_id_variants(user_id: Optional[str]) -> List[str]:
    """E.164-style IDs may appear with or without leading +; merge for capture lookup."""
    if not user_id:
        return []
    u = str(user_id).strip()
    out: List[str] = []
    for cand in (u, u.lstrip("+")):
        if cand and cand not in out:
            out.append(cand)
    digits = u.lstrip("+")
    if digits.isdigit():
        plus = f"+{digits}"
        if plus not in out:
            out.append(plus)
    return out


def dashboard_clear_captured_for_user(user_id: str) -> None:
    for key in _whatsapp_id_variants(user_id):
        dashboard_bot_responses.pop(key, None)


def dashboard_captured_list_for_user(user_id: str) -> List[str]:
    for key in _whatsapp_id_variants(user_id):
        lst = dashboard_bot_responses.get(key)
        if lst:
            return list(lst)
    return []


def _dashboard_empty_capture_hint(user_id: str) -> str:
    return (
        "No response captured: the handler finished but no outbound text was recorded "
        f"(user_id={user_id!r}). Common causes: empty AI reply, template/media-only send, or a bug. "
        "Check the server terminal for DEBUG lines and any GPT/API errors."
    )


async def _await_dashboard_delayed_task(user_id: str) -> Optional[str]:
    """
    Wait for message-combining / GPT task. Uses asyncio.shield so client disconnect or
    upstream cancellation is less likely to cancel the bot mid-reply (empty capture).
    Returns a short diagnostic string when the task did not complete normally (for API hints).
    """
    if user_id not in _delayed_processing_tasks:
        print(f"DEBUG: No delayed task found for user {user_id}")
        return "no_delayed_task_scheduled"
    print(f"DEBUG: Waiting for delayed task for user {user_id} to complete...")
    task = _delayed_processing_tasks[user_id]
    note: Optional[str] = None
    try:
        await asyncio.shield(task)
        print(f"DEBUG: Delayed task completed for user {user_id}")
    except asyncio.CancelledError:
        print(f"DEBUG: Delayed task await cancelled for user {user_id}")
        note = "await_cancelled"
    except Exception as e:
        print(f"DEBUG: Delayed task error: {e}")
        note = str(e)
    finally:
        if user_id in _delayed_processing_tasks:
            del _delayed_processing_tasks[user_id]
    if note is None and task.done():
        if task.cancelled():
            note = "delayed_task_cancelled"
        else:
            exc = task.exception()
            if exc:
                note = str(exc)
    return note


@app.get("/")
async def root():
    return {"message": "Lina's Laser AI Bot is running!"}


@app.get("/api/health")
async def health():
    """Lightweight liveness check - no dependency probes, returns immediately."""
    return {"ok": True, "role": "liveness"}


@app.get("/api/ready")
async def ready():
    """
    Readiness: required dependencies without exposing secrets.
    Authenticated (settings permission) so probe details are not public.
    """
    import os
    from pathlib import Path

    checks = {}
    overall_ok = True

    openai_ok = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    checks["openai_api_key"] = {"ok": openai_ok}
    if not openai_ok:
        overall_ok = False

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        fs_ok = db is not None
        checks["firestore"] = {"ok": fs_ok}
        if not fs_ok:
            overall_ok = False
    except Exception as e:
        checks["firestore"] = {"ok": False, "error": type(e).__name__}
        overall_ok = False

    try:
        from storage.persistent_storage import SETTINGS_DIR, ensure_dirs

        ensure_dirs()
        writable = os.access(str(SETTINGS_DIR), os.W_OK)
        checks["data_root_writable"] = {"ok": writable}
        if not writable:
            overall_ok = False
    except Exception as e:
        checks["data_root_writable"] = {"ok": False, "error": type(e).__name__}
        overall_ok = False

    status = 200 if overall_ok else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status,
        content={"ok": overall_ok, "role": "readiness", "checks": checks},
    )


@app.get("/api/debug/webhook-status")
async def webhook_status():
    """Debug: webhook reachability and config (no secrets). Use when WhatsApp messages don't reach the AI."""
    from modules.webhook_handlers import get_webhook_debug_status
    base = (os.getenv("PUBLIC_URL") or "").strip() or "https://YOUR_SERVER"
    debug = get_webhook_debug_status()
    webhook_url = f"{base.rstrip('/')}/webhook"
    return {
        "ok": True,
        "provider": WhatsAppFactory.get_current_provider(),
        "webhook_url": webhook_url,
        "public_url_configured": bool((os.getenv("PUBLIC_URL") or "").strip()),
        "last_webhook_received": debug.get("last_received_iso"),
        "seconds_since_last_webhook": debug.get("seconds_since_received"),
        "last_parsed_user_id": debug.get("last_parsed_user_id"),
        "hint": "Configure this EXACT URL in MontyMobile dashboard. If Response Body is null in Monty logs, the webhook URL is wrong or the server is unreachable. Set PUBLIC_URL in .env to your domain (e.g. https://linasaibot.com).",
        "test_flow": "POST /api/debug/simulate-webhook with body {\"phone\":\"9613000000\",\"text\":\"مرحبا\"} to test if the flow works.",
    }


@app.post("/api/debug/simulate-webhook")
async def simulate_webhook(req: Request):
    """
    Simulate receiving a webhook (testing only).
    Disabled in production. Requires authenticated testing permission via middleware.
    Body: { "phone": "9613000000", "text": "مرحبا" }
    """
    from modules.api_security import is_production_env

    allow = os.getenv("ALLOW_DEBUG_SIMULATE_WEBHOOK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if is_production_env() or not allow:
        return {
            "success": False,
            "error": "simulate-webhook is disabled (non-production requires ALLOW_DEBUG_SIMULATE_WEBHOOK=true)",
        }
    try:
        from modules.webhook_handlers import process_parsed_message
        try:
            body = await req.json()
        except Exception:
            body = {}
        phone = str(body.get("phone", "9613000000")).strip()
        text = str(body.get("text", "Test message")).strip()
        if not phone:
            return {"success": False, "error": "phone required"}
        adapter = WhatsAppFactory.get_adapter()
        parsed = {
            "user_id": f"+{phone}" if not phone.startswith("+") else phone,
            "user_name": f"Test {phone}",
            "message_id": f"sim_{int(datetime.datetime.now().timestamp() * 1000)}",
            "type": "text",
            "content": {"text": text},
            "phone_number": f"+{phone}" if not phone.startswith("+") else phone,
        }
        await process_parsed_message(parsed, adapter)
        return {"success": True, "message": "Simulated webhook processed", "phone": phone}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


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


async def _test_message_meta_social(
    request: TestMessageRequest,
    start_time: datetime.datetime,
    channel: str,
):
    """Testing Lab Meta social parity path — no real Graph delivery unless explicitly requested."""
    from services.meta_messaging import MetaMessagingSettings, get_meta_messaging_settings
    from services.social_messaging_processor import process_meta_social_event

    sender_id = re.sub(r"\D", "", request.phone or "") or "lab_sender"
    user_id = f"{channel}:{sender_id}"
    dashboard_clear_captured_for_user(user_id)

    async def capture_send(to_number, message_text=None, image_url=None, audio_url=None):
        await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
        return True

    settings = get_meta_messaging_settings()
    # Lab may run without live Meta credentials; supply inert placeholders for identity scoping.
    if not settings.page_access_token:
        settings = MetaMessagingSettings(
            enabled=True,
            page_access_token="lab-simulation-token",
            page_id=settings.page_id or "lab-page",
            instagram_account_id=settings.instagram_account_id or "lab-ig",
            app_secret=settings.app_secret or "",
            verify_token=settings.verify_token or "",
            graph_api_version=settings.graph_api_version or "v24.0",
        )

    event = {
        "channel": channel,
        "sender_id": sender_id,
        "text": request.message,
        "message_id": f"lab_{int(datetime.datetime.now().timestamp() * 1000)}",
        "account_id": settings.instagram_account_id if channel == "instagram" else settings.page_id,
    }
    await process_meta_social_event(
        event,
        settings,
        capture_send=capture_send,
        simulation=True,
        combine_delay=0.0,
    )
    end_time = datetime.datetime.now()
    captured = dashboard_bot_responses.get(user_id) or []
    bot_response = ""
    if captured:
        last = captured[-1]
        bot_response = last.get("text") or last.get("message") or ""
        if isinstance(last, str):
            bot_response = last
    # Normalize capture list shapes
    if not bot_response and isinstance(captured, list):
        for item in reversed(captured):
            if isinstance(item, dict):
                bot_response = item.get("text") or item.get("message") or item.get("content") or ""
            elif isinstance(item, str):
                bot_response = item
            if bot_response:
                break
    return {
        "success": True,
        "bot_response": bot_response,
        "response_time_ms": int((end_time - start_time).total_seconds() * 1000),
        "channel": channel,
        "user_id": user_id,
        "parity_mode": "meta_social",
        "external_delivery": False,
        "simulation": True,
        "note": "Simulated Meta social path — no external Graph send",
    }


@app.post("/api/test-message")
async def test_message(request: TestMessageRequest):
    """Send a test message through the bot.

    Set ``channel`` to ``instagram`` or ``facebook`` to exercise the production
    Meta social path (handoff router, tool exclusion, identity scoping) with a
    capture-only adapter. Omitting channel keeps the legacy WhatsApp-style lab path.
    """
    try:
        start_time = datetime.datetime.now()
        channel = (request.channel or "").strip().lower() or None
        if channel in {"instagram", "facebook"}:
            return await _test_message_meta_social(request, start_time, channel)
        
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
        
        dashboard_clear_captured_for_user(user_id)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None,
                'phone_number': request.phone  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]['phone_number'] = request.phone

        _dash_test_ud = config.user_data_whatsapp[user_id]
        _dash_test_ud["_dashboard_test_simulation"] = True

        # ===== RESTORE USER STATE FROM FIRESTORE (handles server restart) =====
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        async def handle_message_dashboard(user_whatsapp_id: str, user_input_text: str, user_name: str):
            """Dashboard version that captures bot responses WITHOUT saving to Firebase"""
            if user_whatsapp_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_whatsapp_id] = {
                    'user_preferred_lang': 'ar',
                    'initial_user_query_to_process': None,
                    'awaiting_human_handover_confirmation': False,
                    'current_conversation_id': None,
                    'phone_number': request.phone  # Store phone_number for Firestore saves
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
                    send_action_func=send_whatsapp_typing_indicator,
                    skip_firestore_save=True,
                    message_combine_delay=0.0,
                )
            finally:
                # config.TESTING_MODE = False
                # print(f"🧪 TESTING MODE DISABLED - Firebase saving re-enabled")
                pass

        try:
            print(f"DEBUG: Processing message '{request.message}' for user {user_id}")

            handle_err: Optional[str] = None
            delayed_diag: Optional[str] = None
            try:
                await handle_message_dashboard(user_id, request.message, user_name)
                print(f"DEBUG: Message processing completed for user {user_id}")
            except Exception as e:
                handle_err = str(e)
                print(f"DEBUG: Error in handle_message_dashboard: {e}")
                import traceback
                traceback.print_exc()

            if user_id in _delayed_processing_tasks:
                delayed_diag = await _await_dashboard_delayed_task(user_id)

            captured_responses = dashboard_captured_list_for_user(user_id)
            print(f"DEBUG: Captured responses for {user_id}: {captured_responses}")

            _test_ud = config.user_data_whatsapp.get(user_id) or {}
            processing_exception = _test_ud.pop("_dashboard_processing_error", None)

            if captured_responses:
                bot_response = "\n\n".join(captured_responses)
                if processing_exception:
                    bot_response = (
                        f"{bot_response}\n\n——\n[تشخيص السيرفر / Server diagnostic]\n{processing_exception}"
                    )
            elif handle_err:
                bot_response = (
                    f"No response captured: message handler failed before AI ran ({handle_err}). "
                    "See server logs for the full traceback."
                )
            elif delayed_diag:
                bot_response = (
                    f"No response captured: delayed processing note: {delayed_diag}. "
                    "Check server logs."
                )
            elif processing_exception:
                bot_response = (
                    "No bot text was captured; delayed processing raised an error.\n\n"
                    f"[تشخيص السيرفر / Server diagnostic]\n{processing_exception}"
                )
            else:
                bot_response = _dashboard_empty_capture_hint(user_id)

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
                "handler_error": handle_err,
                "delayed_task_note": delayed_diag,
                "processing_exception": processing_exception,
                "provider_info": {
                    "provider": request.provider,
                    "user_id_used": user_id,
                    "adapter_type": type(adapter).__name__
                }
            }
        finally:
            _dash_test_ud.pop("_dashboard_test_simulation", None)

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
        
        dashboard_clear_captured_for_user(user_id)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None,
                'phone_number': request.phone  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]['phone_number'] = request.phone

        # Restore user state from Firestore
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

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

        captured_responses = dashboard_captured_list_for_user(user_id)
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = _dashboard_empty_capture_hint(user_id)
        
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
        
        dashboard_clear_captured_for_user(user_id)
        
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None,
                'phone_number': request.phone  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]['phone_number'] = request.phone

        # Restore user state from Firestore
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        _dash_test_ud_voice = config.user_data_whatsapp[user_id]
        _dash_test_ud_voice["_dashboard_test_simulation"] = True

        async def handle_voice_dashboard(user_whatsapp_id: str, voice_text: str, user_name: str):
            """Dashboard version for voice testing - simulates transcription"""
            if user_whatsapp_id not in config.user_data_whatsapp:
                config.user_data_whatsapp[user_whatsapp_id] = {
                    'user_preferred_lang': 'ar',
                    'initial_user_query_to_process': None,
                    'awaiting_human_handover_confirmation': False,
                    'current_conversation_id': None,
                    'phone_number': request.phone  # Store phone_number for Firestore saves
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
        finally:
            _dash_test_ud_voice.pop("_dashboard_test_simulation", None)

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
        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None,
                'phone_number': request.phone  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]['phone_number'] = request.phone

        # Restore user state from Firestore
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        _dash_test_ud_vt = config.user_data_whatsapp[user_id]
        _dash_test_ud_vt["_dashboard_test_simulation"] = True
        try:
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
                skip_firestore_save=True,
                message_combine_delay=0.0,
            )

            if user_id in _delayed_processing_tasks:
                await _await_dashboard_delayed_task(user_id)

            captured_responses = dashboard_captured_list_for_user(user_id)
            bot_response = (
                "\n\n".join(captured_responses)
                if captured_responses
                else _dashboard_empty_capture_hint(user_id)
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
                    "adapter_type": type(adapter).__name__
                }
            }
        finally:
            _dash_test_ud_vt.pop("_dashboard_test_simulation", None)

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
        
        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None,
                'phone_number': phone  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]['phone_number'] = phone

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
        finally:
            _dash_test_ud_vu.pop("_dashboard_test_simulation", None)

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
        
        dashboard_clear_captured_for_user(user_id)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar',
                'initial_user_query_to_process': None,
                'awaiting_human_handover_confirmation': False,
                'current_conversation_id': None,
                'phone_number': phone  # Store phone_number for Firestore saves
            }
        else:
            # Ensure phone_number is set even for existing user_data
            config.user_data_whatsapp[user_id]['phone_number'] = phone

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

        captured_responses = dashboard_captured_list_for_user(user_id)
        
        if captured_responses:
            bot_response = "\n\n".join(captured_responses)
        else:
            bot_response = _dashboard_empty_capture_hint(user_id)
        
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
