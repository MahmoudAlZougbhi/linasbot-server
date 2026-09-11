"""Customer reply language policy — multilingual by default.

Owners have no Languages tile. Reply language is a global system rule:
detect the customer's language and answer in that language. Franco/Arabizi
is understood as Arabic and always answered in Arabic script.
"""

from __future__ import annotations

from typing import Any

from services.cm.constants import RESPONSE_LANGUAGE_MAP
from services.cm.customer_language_detect import detect_broad_customer_language, normalize_language_code
from services.cm.schemas import LanguagePolicy
from services.cm.version_store import PublishedVersionError, load_published_content

# Frozen fallback when inbound language cannot be detected. Not tenant-configurable.
SYSTEM_DEFAULT_RESPONSE_LANGUAGE = "ar"


def frozen_response_language_map() -> dict[str, str]:
    """Legacy identity map for ar/en/fr/franco (Franco questions → Arabic script replies)."""
    return dict(RESPONSE_LANGUAGE_MAP)


def frozen_language_policy() -> LanguagePolicy:
    """Schema defaults = frozen system standard (Franco → Arabic, default ar)."""
    return LanguagePolicy()


def sanitize_languages_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Force frozen system language fields into a languages section payload."""
    out = dict(payload)
    out["response_language_map"] = frozen_response_language_map()
    out["default_language"] = SYSTEM_DEFAULT_RESPONSE_LANGUAGE
    return out


def load_language_policy(tenant_id: str | None) -> LanguagePolicy:
    """Load published CM Languages, or frozen system defaults when unpublished/invalid."""
    if not tenant_id:
        return frozen_language_policy()
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return frozen_language_policy()
    raw = sections.get("languages")
    if not isinstance(raw, dict):
        return frozen_language_policy()
    try:
        return LanguagePolicy.model_validate(raw)
    except Exception:
        return frozen_language_policy()


def resolve_customer_response_language(
    *,
    tenant_id: str | None,
    detected_language: str | None,
    policy: LanguagePolicy | None = None,
) -> str:
    """Map detected inbound language → customer reply language (no tenant clamp)."""
    _ = (tenant_id, policy)
    default = SYSTEM_DEFAULT_RESPONSE_LANGUAGE

    detected = normalize_language_code(detected_language)
    if not detected:
        return default

    # Arabizi is understood but never used for replies — always Arabic script.
    if detected == "franco":
        return "ar"

    mapping = frozen_response_language_map()
    if detected in mapping:
        mapped = normalize_language_code(mapping.get(detected))
        if mapped == "franco":
            return "ar"
        if mapped:
            return mapped

    # Multilingual: reply in the customer's language (not restricted by supported_languages).
    return detected


def detect_and_resolve_customer_languages(
    *,
    tenant_id: str | None,
    message: str,
    conversation_id: str | None = None,
) -> dict[str, str]:
    """Detect inbound language then resolve reply language (no owner/app override)."""
    cid = (conversation_id or "").strip() or f"cm-lang:{(tenant_id or 'default').strip()}:ephemeral"
    detected_code = detect_broad_customer_language(message=message or "", conversation_id=cid)
    response = resolve_customer_response_language(tenant_id=tenant_id, detected_language=detected_code)
    return {
        "detected_language": detected_code,
        "response_language": response,
    }


def ensure_customer_languages(
    *,
    tenant_id: str | None,
    message: str,
    detected_language: str | None,
    response_language: str | None,
    conversation_id: str | None = None,
) -> tuple[str, str]:
    """Fill missing detected/response language codes before generating a customer reply."""
    detected = normalize_language_code(detected_language)
    response = normalize_language_code(response_language)
    if detected and response:
        return detected, resolve_customer_response_language(
            tenant_id=tenant_id,
            detected_language=detected,
        )
    resolved = detect_and_resolve_customer_languages(
        tenant_id=tenant_id,
        message=message,
        conversation_id=conversation_id,
    )
    if not detected:
        detected = resolved["detected_language"]
    if not response:
        response = resolved["response_language"]
    else:
        response = resolve_customer_response_language(tenant_id=tenant_id, detected_language=detected)
    return detected, response


def language_policy_public_summary(tenant_id: str | None) -> dict[str, Any]:
    """Safe summary for Owner Copilot / diagnostics (not a customer override surface)."""
    pol = load_language_policy(tenant_id)
    return {
        "source": "system_global",
        "supported_languages": list(pol.supported_languages),
        "default_language": SYSTEM_DEFAULT_RESPONSE_LANGUAGE,
        "response_language_map": frozen_response_language_map(),
        "response_language_map_editable": False,
        "customer_reply_multilingual": True,
        "customer_reply_limited_by_supported_languages": False,
        "arabizi_reply_policy": "understand_only_reply_arabic_script",
        "response_language_map_note": (
            "Customer replies are multilingual by default (detect user language, reply in that language). "
            "Arabizi/Franco input always receives Arabic-script replies. "
            "Owners have no Languages tile or reply-language setting."
        ),
        "owner_or_customer_override": False,
        "app_settings_affects_replies": False,
        "editable": [],
        "fixed": [
            "response_language_map",
            "customer_reply_multilingual",
            "default_language",
            "supported_languages",
        ],
    }
