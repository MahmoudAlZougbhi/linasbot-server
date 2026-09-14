"""CM remigrate provenance headers — storage markers, not owner/AI content.

Redistribution prepends ``--- redistributed from ... ---`` so remigrate can
find and replace blocks. That marker must not be shown to owners or models.
"""

from __future__ import annotations

import re
from typing import Any

PROVENANCE_PREFIX = "--- redistributed from "

# Header is prefix … trailing " ---" (body follows on later lines).
_PROVENANCE_HEADER_RE = re.compile(
    rf"{re.escape(PROVENANCE_PREFIX)}.*? ---[ \t]*\n?",
    re.DOTALL,
)

_AI_BASICS_TEXT_FIELDS = (
    "greeting_behavior",
    "short_introduction",
    "identity_summary",
    "advanced_instructions",
)


def strip_provenance_headers(text: str | None) -> str:
    """Remove remigrate provenance headers; keep the redistributed body text."""
    raw = text or ""
    if PROVENANCE_PREFIX not in raw:
        return raw
    return _PROVENANCE_HEADER_RE.sub("", raw).strip()


def sanitize_ai_basics_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Copy ai_basics dict with provenance headers stripped from text fields."""
    out = dict(payload or {})
    for key in _AI_BASICS_TEXT_FIELDS:
        if key in out and isinstance(out[key], str):
            out[key] = strip_provenance_headers(out[key])
    return out


def sanitize_style_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Copy style dict with provenance headers stripped from style_body."""
    out = dict(payload or {})
    body = out.get("style_body")
    if isinstance(body, str):
        out["style_body"] = strip_provenance_headers(body)
    return out


def sanitize_section_payload(section: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Strip remigrate provenance headers from owner-facing CM section payloads."""
    name = (section or "").strip().replace("-", "_")
    if name == "ai_basics":
        return sanitize_ai_basics_payload(payload)
    if name == "style":
        return sanitize_style_payload(payload)
    return dict(payload or {})
