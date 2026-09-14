"""Logical queue classes mapped onto the four HA worker units.

Physical systemd workers stay `high_priority`, `interactive`, `background`,
and `expensive`. Public comments never share the DM/WhatsApp worker list.
"""

from __future__ import annotations

from typing import Final, Literal

from services.queues.config import QUEUE_NAMES

LogicalQueue = Literal[
    "dm_urgent",
    "web_chat",
    "comments",
    "outbound_dm",
    "outbound_comment",
    "outbound_whatsapp",
    "outbound_tiktok",
    "reconcile_dlq",
    "polling",
    "owner_interactive",
    "creative",
]

LOGICAL_QUEUE_TO_PHYSICAL: Final[dict[str, str]] = {
    "dm_urgent": "high_priority",
    "web_chat": "high_priority",
    "outbound_dm": "high_priority",
    "outbound_whatsapp": "high_priority",
    "comments": "background",
    "outbound_comment": "background",
    "outbound_tiktok": "background",
    "reconcile_dlq": "background",
    "polling": "background",
    "owner_interactive": "interactive",
    "creative": "expensive",
}

PRIORITY_ORDER: Final[tuple[str, ...]] = (
    "dm_urgent",
    "outbound_whatsapp",
    "outbound_dm",
    "web_chat",
    "comments",
    "outbound_comment",
    "outbound_tiktok",
    "reconcile_dlq",
    "polling",
    "owner_interactive",
    "creative",
)


def physical_queue_for(logical: str) -> str:
    mapped = LOGICAL_QUEUE_TO_PHYSICAL.get(str(logical or "").strip())
    if mapped in QUEUE_NAMES:
        return mapped
    raise ValueError(f"unknown logical queue: {logical}")


def logical_for_channel(*, channel: str, surface: str) -> str:
    ch = (channel or "").strip().lower()
    surf = (surface or "").strip().lower()
    if surf == "operator":
        if ch == "tiktok":
            return "outbound_tiktok"
        return "outbound_dm"
    if surf == "web_chat" or ch == "web_chat":
        return "web_chat"
    if surf == "comment":
        return "comments"
    if ch == "whatsapp":
        return "dm_urgent"
    if surf == "dm":
        return "dm_urgent"
    return "comments"


def outbound_logical(*, channel: str, surface: str) -> str:
    ch = (channel or "").strip().lower()
    surf = (surface or "").strip().lower()
    if surf == "operator":
        return "outbound_dm"
    if ch == "whatsapp":
        return "outbound_whatsapp"
    if ch == "tiktok":
        return "outbound_tiktok"
    if surf == "comment":
        return "outbound_comment"
    return "outbound_dm"
