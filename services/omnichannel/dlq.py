"""Durable dead-letter alerts. Replay is delivery-only; never regenerate AI."""

from __future__ import annotations

import logging
from typing import Any

from services.omnichannel import metrics

_log = logging.getLogger("uvicorn.error")


def mark_dead_letter(*, event_id: str, reason: str, channel: str = "", kind: str = "") -> None:
    metrics.inbound_dead_letter(channel=channel or kind or "unknown")
    _log.error(
        "[omnichannel-dlq] channel=%s event_id=%s reason=%s",
        channel,
        event_id,
        (reason or "unknown")[:180],
    )


def mark_needs_owner_action(*, event_id: str, kind: str, reason: str) -> None:
    metrics.inbound_dead_letter(channel=kind or "unknown")
    _log.error(
        "[omnichannel] needs_owner_action event_id=%s kind=%s reason=%s",
        event_id,
        kind,
        (reason or "unknown")[:180],
    )


def replay_delivery_only(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("mode") or "") != "delivery_only":
        raise PermissionError("omnichannel_replay_delivery_only_required")
    if payload.get("regenerate_ai") is True:
        raise PermissionError("omnichannel_replay_must_not_regenerate")
    return {"ok": True, "mode": "delivery_only"}
