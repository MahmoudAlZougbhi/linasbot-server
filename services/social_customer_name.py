"""Resolve Meta participant display names for Live Chat + AI context."""

from __future__ import annotations

from typing import Any

import config
from services.meta_messaging import (
    SOCIAL_DISPLAY_NAME_FALLBACK,
    MetaMessagingAdapter,
    is_unresolved_social_display_name,
    pick_meta_participant_display_name,
)
from utils.utils import save_user_name_to_firestore


async def resolve_social_customer_display_name(
    *,
    user_id: str,
    sender_id: str,
    event: dict[str, Any],
    adapter: MetaMessagingAdapter | None,
    persisted_state: dict[str, Any] | None,
    skip_persist: bool,
) -> str:
    """
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

    config.user_names[user_id] = SOCIAL_DISPLAY_NAME_FALLBACK
    return SOCIAL_DISPLAY_NAME_FALLBACK
