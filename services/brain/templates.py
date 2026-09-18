"""Owner-authored Brain protocol copy only. Empty means customer silence."""

from __future__ import annotations


def _lang(code: str) -> str:
    raw = (code or "en").strip().lower()
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("fr"):
        return "fr"
    return "en"


def owner_protocol_text(key: str, response_language: str = "") -> str:
    """Owner-authored dynamic message only. Empty when the tenant has no verbatim copy."""
    lang = _lang(response_language)
    mapped = {
        "handoff": "brain_handoff_ack",
        "confirm_request": "brain_confirm_request",
        "visual_disabled": "brain_visual_disabled",
        "no_evidence": "brain_no_evidence",
        "no_evidence_handoff": "brain_no_evidence_handoff",
        "faq_ambiguous": "brain_faq_ambiguous",
    }.get(key)
    if not mapped:
        return ""
    try:
        from services.owner_copilot.dynamic_messages_service import get_persisted_dynamic_message

        text = (get_persisted_dynamic_message(mapped, lang) or "").strip()
        if text and text != mapped:
            return text
    except Exception:
        pass
    return ""


def brain_template(key: str, response_language: str = "") -> str:
    """Alias for owner_protocol_text. Never invents canned EN/AR/FR fallbacks."""
    return owner_protocol_text(key, response_language)
