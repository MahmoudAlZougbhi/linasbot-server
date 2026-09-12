"""WhatsApp Postgres is only for WA Cloud Live Chat — never Meta/TikTok operator sends."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def live_chat_manual_mode_db_session(
    *,
    user_id: str,
    tenant_id: str | None,
    source_channel: str | None,
) -> Iterator[tuple[Any, str | None]]:
    from services.live_chat_operator_social_delivery import (
        infer_live_chat_source_channel,
        live_chat_needs_whatsapp_session,
    )

    channel = infer_live_chat_source_channel(user_id, source_channel)
    if not live_chat_needs_whatsapp_session(
        user_id=user_id,
        tenant_id=tenant_id,
        source_channel=channel,
    ):
        yield None, channel
        return

    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

    wa_cm = None
    session = None
    try:
        wa_cm = whatsapp_session()
        session = wa_cm.__enter__()
    except WhatsAppDatabaseUnavailable:
        yield None, channel
        return
    try:
        yield session, channel
        if session is not None:
            session.commit()
    finally:
        if wa_cm is not None:
            wa_cm.__exit__(None, None, None)


def operator_thread_status(*, paused: bool, undone: bool = False) -> str:
    if undone or not paused:
        return "bot"
    return "human"
