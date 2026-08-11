"""Dashboard debug + Testing Lab message/image leftovers (LOC split).

Lab HTTP handlers refuse with 403; bodies retained for reference until product cleanup.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any

from fastapi import Request

import config
from handlers.photo_handlers import handle_photo_message
from handlers.text_handlers import _delayed_processing_tasks, handle_message
from modules.core import app, dashboard_bot_responses, dashboard_stats
from modules.dashboard_api_helpers import (
    _await_dashboard_delayed_task,
    _dashboard_empty_capture_hint,
    _refuse_disabled_lab_endpoint,
    dashboard_captured_list_for_user,
    dashboard_clear_captured_for_user,
    dashboard_send_message_capture,
    restore_user_state_from_firestore,
)
from modules.models import ProviderSwitchRequest, TestImageRequest, TestMessageRequest
from modules.whatsapp_adapters import send_whatsapp_typing_indicator
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory


@app.get("/api/debug/webhook-status")
async def webhook_status() -> Any:
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
        "test_flow": 'POST /api/debug/simulate-webhook with body {"phone":"9613000000","text":"مرحبا"} to test if the flow works.',
    }


@app.post("/api/debug/simulate-webhook")
async def simulate_webhook(req: Request) -> Any:
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
async def test_api() -> Any:
    """Legacy Testing Lab health probe — disabled for all tenants."""
    _refuse_disabled_lab_endpoint()


@app.post("/api/switch-provider")
async def switch_provider(request: ProviderSwitchRequest) -> Any:
    """HTTP provider switching is permanently refused (no process-global WA switch via API)."""
    _refuse_disabled_lab_endpoint()


async def _test_message_meta_social(
    request: TestMessageRequest,
    start_time: datetime.datetime,
    channel: str,
) -> Any:
    """Testing Lab Meta social parity path — no real Graph delivery unless explicitly requested."""
    from services.meta_messaging import MetaMessagingSettings, get_meta_messaging_settings
    from services.social_messaging_processor import process_meta_social_event

    sender_id = re.sub(r"\D", "", request.phone or "") or "lab_sender"
    user_id = f"{channel}:{sender_id}"
    dashboard_clear_captured_for_user(user_id)

    async def capture_send(
        to_number: Any, message_text: Any | None = None, image_url: Any | None = None, audio_url: Any | None = None
    ) -> Any:
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
    if isinstance(captured, list):
        for item in reversed(captured):
            if isinstance(item, str) and item.strip():
                bot_response = item.strip()
                break
            if isinstance(item, dict):
                candidate = item.get("text") or item.get("message") or item.get("content") or ""
                if isinstance(candidate, str) and candidate.strip():
                    bot_response = candidate.strip()
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
async def test_message(request: TestMessageRequest) -> Any:
    """Send a test message through the bot.

    Set ``channel`` to ``instagram`` or ``facebook`` to exercise the production
    Meta social path (handoff router, tool exclusion, identity scoping) with a
    capture-only adapter. Omitting channel keeps the legacy WhatsApp-style lab path.
    """
    _refuse_disabled_lab_endpoint()
    try:
        start_time = datetime.datetime.now()
        channel = (request.channel or "").strip().lower() or None
        if channel in {"instagram", "facebook"}:
            return await _test_message_meta_social(request, start_time, channel)

        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print("=== DASHBOARD TEST ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Adapter type: {type(adapter).__name__}")
            print(f"Current provider: {WhatsAppFactory.get_current_provider()}")
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

        _dash_test_ud = config.user_data_whatsapp[user_id]
        _dash_test_ud["_dashboard_test_simulation"] = True

        # ===== RESTORE USER STATE FROM FIRESTORE (handles server restart) =====
        restored_name = await restore_user_state_from_firestore(user_id)
        if restored_name:
            user_name = restored_name

        async def handle_message_dashboard(user_whatsapp_id: str, user_input_text: str, user_name: str) -> Any:
            """Dashboard version that captures bot responses WITHOUT saving to Firebase"""
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

                if request.provider == "qiscus":
                    try:
                        print(f"DEBUG: Testing Qiscus send with room_id: {to_number}")
                        result = await adapter.send_text_message(to_number, message_text or "")
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

            handle_err: str | None = None
            delayed_diag: str | None = None
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
            cm_diagnostics = _test_ud.pop("_dashboard_cm_diagnostics", None)

            if captured_responses:
                bot_response = "\n\n".join(captured_responses)
                if processing_exception:
                    bot_response = f"{bot_response}\n\n——\n[تشخيص السيرفر / Server diagnostic]\n{processing_exception}"
            elif handle_err:
                bot_response = (
                    f"No response captured: message handler failed before AI ran ({handle_err}). "
                    "See server logs for the full traceback."
                )
            elif delayed_diag:
                bot_response = f"No response captured: delayed processing note: {delayed_diag}. Check server logs."
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
            dashboard_stats["conversations"].append(
                {
                    "user": user_name,
                    "message": request.message,
                    "bot_response": bot_response,
                    "timestamp": start_time.isoformat(),
                    "provider": request.provider,
                }
            )

            return {
                "success": True,
                "message": "Test message processed",
                "response_time_ms": response_time,
                "bot_response": bot_response,
                "handler_error": handle_err,
                "delayed_task_note": delayed_diag,
                "processing_exception": processing_exception,
                "cm_diagnostics": cm_diagnostics,
                "provider_info": {
                    "provider": request.provider,
                    "user_id_used": user_id,
                    "adapter_type": type(adapter).__name__,
                },
            }
        finally:
            _dash_test_ud.pop("_dashboard_test_simulation", None)

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-image")
async def test_image(request: TestImageRequest) -> Any:
    """Test image analysis through the bot with image URL"""
    _refuse_disabled_lab_endpoint()
    try:
        start_time = datetime.datetime.now()

        try:
            adapter = WhatsAppFactory.switch_provider(request.provider)
            print("=== IMAGE URL TEST ===")
            print(f"Switched to provider: {request.provider}")
            print(f"Image URL: {request.image_url}")
            print(f"Caption: {request.caption}")
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

        async def capture_send_message(
            to_number: str, message_text: str | None = None, image_url: str | None = None, audio_url: str | None = None
        ) -> Any:
            await dashboard_send_message_capture(to_number, message_text, image_url, audio_url)
            return True

        try:
            await handle_photo_message(
                user_id=user_id,
                user_name=user_name,
                image_url=request.image_url,
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
                "message": f"[Image: {request.image_url}] {request.caption}",
                "bot_response": bot_response,
                "timestamp": start_time.isoformat(),
                "provider": request.provider,
            }
        )

        return {
            "success": True,
            "message": "Test image processed",
            "response_time_ms": response_time,
            "bot_response": bot_response,
            "provider_info": {
                "provider": request.provider,
                "user_id_used": user_id,
                "adapter_type": type(adapter).__name__,
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
