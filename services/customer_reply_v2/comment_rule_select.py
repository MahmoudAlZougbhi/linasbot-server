"""Which Comment Rules Luna may retrieve (AI-guidance only)."""

from __future__ import annotations

from typing import Any


def is_luna_selectable_comment_rule(raw: dict[str, Any]) -> bool:
    """Deterministic templates stay server-enforced. AI-guidance is selectable evidence."""
    if not isinstance(raw, dict):
        return False
    if raw.get("enabled") is False:
        return False
    status = str(raw.get("status") or "").strip().lower()
    if status in {"deleted", "archived", "inactive"}:
        return False
    mode = str(raw.get("rule_mode") or "").strip().lower()
    template = str(raw.get("reply_template") or "").strip()
    action = str(raw.get("action") or "").strip()
    if mode == "deterministic":
        return False
    if not mode and (action == "ignore" or bool(template)):
        return False
    return True
