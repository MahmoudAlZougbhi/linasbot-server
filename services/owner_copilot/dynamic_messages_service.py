"""Tenant published dynamic messages. Missing text means silence."""

from __future__ import annotations


def get_tenant_dynamic_message(tenant_id: str, key: str, lang: str = "ar") -> str:
    """Read one published CM dynamic_messages item. No global catalog and no fallback copy."""
    tid = str(tenant_id or "").strip()
    message_key = str(key or "").strip()
    if not tid or not message_key:
        return ""
    from services.brain.greeting_policy import load_dynamic_messages

    section = load_dynamic_messages(tid)
    if section is None:
        return ""
    lang_key = (lang or "").strip().lower()
    for item in section.items:
        if not item.enabled:
            continue
        if item.id != message_key and (item.name or "").strip() != message_key:
            continue
        if lang_key == "franco":
            return str(item.ar or "").strip()
        if lang_key not in {"ar", "en", "fr"}:
            return ""
        return str(getattr(item, lang_key, "") or "").strip()
    return ""


def get_dynamic_message(key: str, lang: str = "ar", tenant_id: str | None = None) -> str:
    """Compatibility wrapper. Without a tenant id the result is empty."""
    return get_tenant_dynamic_message(str(tenant_id or ""), key, lang)


def get_owner_persisted_message(key: str, lang: str = "ar") -> str:
    """Global file copy is not a customer reply. Callers that still patch this get silence."""
    del key, lang
    return ""
