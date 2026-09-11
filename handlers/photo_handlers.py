from __future__ import annotations

from typing import Any

from handlers.training_handlers import handle_training_input
from services.analytics_events import analytics  # noqa: F401 — kept for training path imports
from utils.utils import notify_human_on_whatsapp  # noqa: F401


async def handle_photo_message(
    user_id: str, user_name: str, image_url: str, user_data: dict, send_message_func: Any, send_action_func: Any
) -> Any:
    """
    Photo inbound → Customer Brain permanent path (no legacy vision reply engine).
    Training mode still uses the training handler.
    """
    import config

    config.user_names[user_id] = user_name
    tenant_id = str(user_data.get("tenant_id") or "").strip()
    if not tenant_id:
        print("ERROR: photo handler refused — tenant_id required")
        return

    if config.user_in_training_mode.get(user_id, False):
        await handle_training_input(
            user_id=user_id,
            user_name=user_name,
            image_url=image_url,
            user_data=user_data,
            send_message_func=send_message_func,
            send_action_func=send_action_func,
        )
        return

    from handlers.text_handlers_respond import _process_and_respond
    from services.ai_reply_delivery import wrap_tracked_send
    from services.ai_reply_turn_runtime import run_reserved_customer_turn
    from services.customer_reply_v2.inbound_media import mark_inbound_attachment, store_inbound_image_base64

    if not user_data.get("_source_message_id") and image_url:
        user_data["_source_message_id"] = str(image_url)
    if str(image_url or "").startswith("data:"):
        store_inbound_image_base64(user_data, b64=image_url)
    elif image_url:
        from services.customer_reply_v2.inbound_media import store_inbound_image_from_url

        await store_inbound_image_from_url(user_data, image_url)
    else:
        mark_inbound_attachment(user_data, "image")

    tracked_send = wrap_tracked_send(send_message_func, user_data)
    await run_reserved_customer_turn(
        user_data,
        lambda: _process_and_respond(
            user_id,
            user_name,
            "[صورة]",
            user_data,
            tracked_send,
            send_action_func,
        ),
    )
