"""Reply-text helpers for the published CM inbound path."""

from __future__ import annotations

import json
import re


def _unwrap_embedded_json_reply(text: str) -> str:
    """Unwrap nested {"action": "...", "bot_reply": "..."} so users only see text."""
    value = str(text or "").strip()
    for _ in range(3):
        if not value.startswith("{"):
            break
        try:
            parsed = json.loads(value)
        except Exception:
            break
        if not isinstance(parsed, dict) or "bot_reply" not in parsed:
            break
        value = str(parsed.get("bot_reply") or "").strip()
    return value


def _clean_reply_text(text: str) -> str:
    value = _unwrap_embedded_json_reply(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{2,}", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()
