"""Bridge normalized Meta social events into the existing AI conversation pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import config
from handlers.text_handlers import handle_message
from handlers.text_handlers_firestore import _delayed_processing_tasks
from services.meta_messaging import (
    MetaMessagingAdapter,
    MetaMessagingSettings,
    resolve_meta_send_account_id,
)
from utils.utils import get_user_state_from_firestore

SendFunc = Callable[..., Awaitable[Any]]


async def _await_delayed_processing(user_id: str) -> None:
    task = _delayed_processing_tasks.get(user_id)
    if not task:
        return
    try:
        await task
    finally:
        _delayed_processing_tasks.pop(user_id, None)


async def process_meta_social_event(
    event: dict,
    settings: MetaMessagingSettings,
    *,
    capture_send: SendFunc | None = None,
    simulation: bool = False,
    combine_delay: float | None = None,
) -> None:
    """
    Process one normalized Meta IG/FB event through the canonical AI path.

    When ``simulation`` is True (Testing Lab), external Graph sends are skipped and
    ``capture_send`` is used instead. Production webhooks must leave simulation=False.
    """
    channel = str(event["channel"])
    sender_id = str(event["sender_id"])
    user_id = f"{channel}:{sender_id}"
    account_id = resolve_meta_send_account_id(channel, event, settings)

    adapter = None
    if not simulation:
        adapter = MetaMessagingAdapter(
            access_token=settings.page_access_token,
            account_id=account_id,
            channel=channel,
            graph_api_version=settings.graph_api_version,
        )
    try:
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
                **config.DEFAULT_CONVERSATION_STATE,
            }
        user_data = config.user_data_whatsapp[user_id]
        user_data.update(
            {
                "channel": channel,
                "social_sender_id": sender_id,
                "meta_account_id": account_id,
                # Namespaced non-phone identity so CRM phone tools never treat this as a mobile.
                "phone_number": f"room:{user_id}",
                "_source_message_id": str(event.get("message_id") or ""),
            }
        )
        if simulation:
            user_data["_meta_social_lab_simulation"] = True
        # Bounded handoff TTL: drop expired channel-scoped social_contact_flow blobs.
        from services.social_contact_routing import expire_social_contact_flows_in_user_data

        expire_social_contact_flows_in_user_data(user_data)
        if not config.user_names.get(user_id):
            config.user_names[user_id] = "Instagram Customer" if channel == "instagram" else "Facebook Customer"

        if config.user_gender.get(user_id) not in {"male", "female"}:
            try:
                persisted = await get_user_state_from_firestore(user_id)
                persisted_gender = (persisted or {}).get("gender")
                if persisted_gender in {"male", "female"}:
                    config.user_gender[user_id] = persisted_gender
            except Exception as exc:
                print(f"[meta-social] state restore skipped for {user_id}: {exc}")

        text = str(event.get("text") or "").strip()
        if not text and event.get("attachments"):
            text = "أرسلت صورة أو ملف. اكتبلي شو حابب تعرف عنه كرمال ساعدك."
        if not text:
            return

        async def send_message(
            _namespaced_id: str,
            message_text: str | None = None,
            image_url: str | None = None,
            audio_url: str | None = None,
        ) -> Any:
            if capture_send is not None:
                await capture_send(_namespaced_id, message_text, image_url, audio_url)
                return {
                    "success": True,
                    "simulated": True,
                    "delivered_externally": False,
                }
            if adapter is None:
                return {"success": False, "error": "Meta adapter unavailable"}
            if message_text:
                return await adapter.send_text_message(sender_id, message_text)
            return {"success": False, "error": "Only text replies are enabled for Meta social DMs"}

        async def send_action(_namespaced_id: str) -> Any:
            if simulation or adapter is None:
                return {"success": True, "simulated": True}
            return await adapter.send_typing(sender_id)

        skip_firestore_save = bool(simulation)
        message_combine_delay: float | None = None
        if simulation:
            message_combine_delay = 0.0 if combine_delay is None else float(combine_delay)

        await handle_message(
            user_id=user_id,
            user_name=config.user_names[user_id],
            user_input_text=text,
            user_data=user_data,
            send_message_func=send_message,
            send_action_func=send_action,
            skip_firestore_save=skip_firestore_save,
            message_combine_delay=message_combine_delay,
        )
        await _await_delayed_processing(user_id)
    finally:
        if adapter is not None:
            await adapter.close()
