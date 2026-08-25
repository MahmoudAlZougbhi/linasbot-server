"""Best-effort PostgreSQL mirror of Meta inbound. Firestore remains Meta SoT."""

from __future__ import annotations

import logging
import time
from typing import Any

from services.omnichannel.contract import NormalizedInbound
from services.omnichannel.store import payload_hash, persist_inbound

_log = logging.getLogger("uvicorn.error")


def dual_write_inbound(event: NormalizedInbound) -> None:
    try:
        from db.session import whatsapp_session

        with whatsapp_session() as session:
            persist_inbound(session, event)
            session.commit()
    except Exception:
        _log.warning("[omnichannel] dual_write_failed channel=%s surface=%s", event.channel, event.surface)


def mirror_meta_inbound(record: Any) -> None:
    kind = str(getattr(record, "kind", "") or "")
    binding = getattr(record, "binding_snapshot", None) or {}
    channel = str(binding.get("channel") or "").strip().lower()
    if channel not in {"instagram", "facebook"}:
        channel = "instagram" if "instagram" in kind else "facebook"
    surface = "comment" if kind == "meta_comment" else "dm"
    payload = dict(getattr(record, "payload", None) or {})
    dual_write_inbound(
        NormalizedInbound(
            provider_event_id=str(getattr(record, "event_id", "") or "")[:128],
            tenant_id=str(getattr(record, "tenant_id", "") or ""),
            account_id=str(binding.get("asset_id") or "")[:128],
            channel=channel,  # type: ignore[arg-type]
            surface=surface,  # type: ignore[arg-type]
            conversation_key=str(getattr(record, "conversation_key", "") or "")[:255],
            provider_timestamp=float(getattr(record, "created_at", 0) or time.time()),
            payload_hash=payload_hash(payload) if payload else str(getattr(record, "event_id", "") or ""),
            payload={**payload, "_mirror_only": True},
        )
    )
