"""Pick the Meta DM binding that can actually send to the inbound recipient."""

from __future__ import annotations

from typing import Any

from services.meta_instagram_login_capabilities import select_instagram_binding_for_capability


def select_binding_for_meta_dm(
    candidates: list[Any],
    *,
    channel: str,
    registry: Any,
) -> Any | None:
    """Prefer ready Instagram Login for IG DMs; otherwise first candidate."""

    if not candidates:
        return None
    ch = str(channel or "").strip().lower()
    if ch == "instagram":
        selected = select_instagram_binding_for_capability(candidates, "dm", registry=registry)
        if selected is not None:
            return selected
    return candidates[0]
