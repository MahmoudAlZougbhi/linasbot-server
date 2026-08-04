"""Bridge normalized Meta social events into the existing AI conversation pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import config
from handlers.text_handlers import handle_message
from handlers.text_handlers_firestore import _delayed_processing_tasks
from services.meta_messaging import (
    SOCIAL_DISPLAY_NAME_FALLBACK,
    MetaMessagingAdapter,
    MetaMessagingSettings,
    is_unresolved_social_display_name,
    pick_meta_participant_display_name,
    resolve_meta_send_account_id,
)
from utils.utils import get_user_state_from_firestore, save_user_name_to_firestore

SendFunc = Callable[..., Awaitable[Any]]


async def _await_delayed_processing(user_id: str) -> None:
    task = _delayed_processing_tasks.get(user_id)
    if not task:
        return
    try:
        await task
    finally:
        _delayed_processing_tasks.pop(user_id, None)


async def _resolve_social_customer_display_name(
    *,
    user_id: str,
    sender_id: str,
    event: dict[str, Any],
    adapter: MetaMessagingAdapter | None,
    persisted_state: dict[str, Any] | None,
    skip_persist: bool,
) -> str:
    """
    Resolve the Meta participant's display name for Live Chat + AI context.

    Order: webhook fields → in-memory → Firestore → Graph User Profile → honest fallback.
    Never invent names. Never keep "Instagram Customer" / "Facebook Customer".
    """
    webhook_name = pick_meta_participant_display_name(
        name=str(event.get("sender_name") or event.get("name") or ""),
        username=str(event.get("sender_username") or event.get("username") or ""),
    )
    if webhook_name:
        config.user_names[user_id] = webhook_name
        if not skip_persist:
            try:
                await save_user_name_to_firestore(user_id, webhook_name)
            except Exception as exc:
                print(f"[meta-social] name_persist_skipped type={type(exc).__name__}")
        return webhook_name

    cached = str(config.user_names.get(user_id) or "").strip()
    if cached and not is_unresolved_social_display_name(cached):
        return cached

    persisted_name = pick_meta_participant_display_name(name=(persisted_state or {}).get("name"))
    if persisted_name:
        config.user_names[user_id] = persisted_name
        return persisted_name

    if adapter is not None:
        profile = await adapter.fetch_participant_profile(sender_id)
        graph_name = pick_meta_participant_display_name(
            name=profile.get("name"),
            first_name=profile.get("first_name"),
            last_name=profile.get("last_name"),
            username=profile.get("username"),
        )
        if graph_name:
            config.user_names[user_id] = graph_name
            if not skip_persist:
                try:
                    await save_user_name_to_firestore(user_id, graph_name)
                except Exception as exc:
                    print(f"[meta-social] name_persist_skipped type={type(exc).__name__}")
            return graph_name

    # Honest temporary label — not channel-branded placeholders.
    config.user_names[user_id] = SOCIAL_DISPLAY_NAME_FALLBACK
    return SOCIAL_DISPLAY_NAME_FALLBACK


async def process_meta_social_event(
    event: dict[str, Any],
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
    tenant_id = str(event.get("tenant_id") or settings.tenant_id or "linas").strip()
    # Preserve Lina's established identities/state while namespacing every future
    # SaaS tenant so two businesses can never share customer state.
    user_id = f"{channel}:{sender_id}" if tenant_id == "linas" else f"{tenant_id}:{channel}:{sender_id}"
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
                "tenant_id": tenant_id,
                "meta_app_key": str(event.get("meta_app_key") or settings.app_key),
                "meta_binding_id": str(event.get("meta_binding_id") or settings.binding_id),
                # Namespaced non-phone identity so CRM phone tools never treat this as a mobile.
                "phone_number": f"room:{user_id}",
                "_source_message_id": str(event.get("message_id") or ""),
            }
        )
        if simulation:
            user_data["_meta_social_lab_simulation"] = True
        # Bounded handoff TTL: drop expired channel-scoped social_contact_flow blobs.
        from services.social_contact_routing import (
            expire_social_contact_flows_in_user_data,
            restore_social_booking_preference,
        )

        expire_social_contact_flows_in_user_data(user_data)

        persisted_state: dict[str, Any] = {}
        try:
            persisted_state = await get_user_state_from_firestore(user_id) or {}
        except Exception as exc:
            # A social identity contains a platform-scoped sender ID. Keep it and
            # exception text out of logs; the error type is sufficient to operate.
            print(f"[meta-social] state_restore_skipped type={type(exc).__name__}")

        restore_social_booking_preference(user_data, persisted_state)

        display_name = await _resolve_social_customer_display_name(
            user_id=user_id,
            sender_id=sender_id,
            event=event,
            adapter=adapter,
            persisted_state=persisted_state,
            skip_persist=bool(simulation),
        )

        # Social booking uses only the scope-isolated customer-selected preference
        # restored above.  Do not restore the legacy unscoped profile gender here.

        text = str(event.get("text") or "").strip()
        attachments = event.get("attachments") or []
        image_attachment_count = 0
        if isinstance(attachments, list):
            for item in attachments:
                if isinstance(item, dict) and str(item.get("type") or "").lower() == "image":
                    image_attachment_count += 1
                elif item:
                    image_attachment_count += 1
        if image_attachment_count > 0:
            from services.ai_limits_enforcement import (
                customer_image_limit_message,
                enforce_image_analysis_quota,
            )

            # Count each inbound image toward the per-end-user quota even when
            # Meta social path does not yet run full vision analysis.
            image_quota = enforce_image_analysis_quota(
                user_id=user_id,
                user_data=user_data,
                amount=image_attachment_count,
                consume=True,
            )
            if not image_quota.allowed:
                limit_msg = customer_image_limit_message(image_quota)
                if capture_send is not None:
                    await capture_send(user_id, limit_msg, None, None)
                elif adapter is not None:
                    await adapter.send_text_message(sender_id, limit_msg)
                print(
                    f"[ai_limits] social_image_blocked tenant={tenant_id} "
                    f"count={image_attachment_count} reason={image_quota.reason}",
                    flush=True,
                )
                return

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
            user_name=display_name,
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
