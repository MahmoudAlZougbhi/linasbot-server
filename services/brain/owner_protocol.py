"""Owner-authored Brain protocol copy. Empty when the tenant has not saved verbatim text."""

from __future__ import annotations


def _lang(code: str) -> str:
    raw = (code or "en").strip().lower()
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("fr"):
        return "fr"
    return "en"


def owner_protocol_text(key: str, response_language: str = "") -> str:
    """Owner-persisted dynamic message only. Catalog defaults never reach customers."""
    lang = _lang(response_language)
    mapped = {
        "handoff": "brain_handoff_ack",
        "confirm_request": "brain_confirm_request",
        "waiting_queue": "waiting_queue_message",
    }.get(key)
    if not mapped:
        return ""
    try:
        from services.owner_copilot.dynamic_messages_service import get_owner_persisted_message

        text = (get_owner_persisted_message(mapped, lang) or "").strip()
        if text and text != mapped:
            return text
    except Exception:
        pass
    return ""
