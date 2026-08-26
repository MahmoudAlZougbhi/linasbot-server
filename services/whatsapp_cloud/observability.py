"""Safe observability helpers — never log tokens, secrets, or message bodies."""

from __future__ import annotations

import json
import time
from typing import Any

from services.whatsapp_cloud.redaction import redact_whatsapp_text

_SECRET_KEYS = frozenset({"access_token", "token", "code", "text", "body", "secret", "app_secret"})


def emit_wa_event(event: str, **fields: Any) -> None:
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if key in _SECRET_KEYS:
            continue
        safe[key] = redact_whatsapp_text(value) if isinstance(value, str) else value
    payload = {"ts": time.time(), "domain": "whatsapp_cloud", "event": event, **safe}
    print(f"[whatsapp_cloud] {json.dumps(payload, default=str, separators=(',', ':'))}", flush=True)


def record_analytics_channel_usage(
    *,
    tenant_id: str,
    connection_id: str,
    conversation_id: str,
    provider_message_id: str,
    source: str,
) -> None:
    """Attach standardized WhatsApp channel metadata to analytics without secrets."""

    try:
        from services.interaction_flow_logger import log_interaction

        log_interaction(
            user_id=f"wa:{conversation_id}",
            user_message="[redacted]",
            bot_to_user="[redacted]",
            source=source,
            channel="whatsapp",
            conversation_id=conversation_id,
            message_id=(provider_message_id or "")[:64],
            handler_path="whatsapp_cloud",
            outcome="ok",
            cm_diagnostics={"tenant_id": tenant_id, "connection_id": connection_id},
        )
    except Exception as exc:
        emit_wa_event("analytics_emit_failed", error=type(exc).__name__)
    emit_wa_event(
        "analytics_usage",
        tenant_id=tenant_id,
        connection_id=connection_id,
        conversation_id=conversation_id,
        provider_message_id_prefix=(provider_message_id or "")[:12],
        source=source,
        channel="whatsapp",
    )
