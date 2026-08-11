"""Dashboard API capture/helpers shared by health and lab routes (LOC split)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException

import config
from handlers.text_handlers import _delayed_processing_tasks
from modules.core import dashboard_bot_responses
from services.product_features import DISABLED_PRODUCT_MESSAGE


def _refuse_disabled_lab_endpoint() -> None:
    """Defense-in-depth: Testing Lab / provider-switch HTTP surface is product-disabled."""
    raise HTTPException(status_code=403, detail=DISABLED_PRODUCT_MESSAGE)


async def restore_user_state_from_firestore(user_id: str) -> str:
    """
    Restore user state (gender, name, greeting_stage) from Firestore.
    Returns the restored name if found, otherwise returns None.
    This is needed for dashboard test endpoints which bypass webhook_handlers.
    """
    current_gender = config.user_gender.get(user_id)
    restored_name: str | None = None

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

    return restored_name or ""


async def dashboard_send_message_capture(
    to_number: str, message_text: str | None = None, image_url: str | None = None, audio_url: str | None = None
) -> Any:
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


def _whatsapp_id_variants(user_id: str | None) -> list[str]:
    """E.164-style IDs may appear with or without leading +; merge for capture lookup."""
    if not user_id:
        return []
    u = str(user_id).strip()
    out: list[str] = []
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


def dashboard_captured_list_for_user(user_id: str) -> list[str]:
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


async def _await_dashboard_delayed_task(user_id: str) -> str | None:
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
    note: str | None = None
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
