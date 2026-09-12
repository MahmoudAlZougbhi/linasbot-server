"""Customer-facing human handover copy from AI Setup. Never interpolates staff email."""

from __future__ import annotations

from services.dynamic_messages_service import get_dynamic_message


def customer_human_handover_notice(lang: str) -> str:
    lang_key = (lang or "ar").strip().lower() or "ar"
    text = str(get_dynamic_message("human_handover_message", lang_key) or "").strip()
    if text:
        return text
    return str(get_dynamic_message("human_handover_message", "ar") or "").strip()


def public_staff_label(*candidates: object) -> str:
    """Inbox/staff label only. Never returns a raw email address."""
    for raw in candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        if "@" in text:
            local = text.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
            if not local:
                continue
            return " ".join(part.capitalize() for part in local.split() if part)
        return text
    return ""
