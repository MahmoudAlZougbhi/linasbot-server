"""Customer reply language from AI Setup Languages (system standard).

App UI locale / owner preferred_language do not choose DM or comment reply language.
End customers cannot override reply language; inbound detection only feeds the CM map.
"""

from __future__ import annotations

from typing import Any

from services.cm.constants import RESPONSE_LANGUAGE_MAP, SUPPORTED_LANGUAGES
from services.cm.schemas import LanguagePolicy
from services.cm.version_store import PublishedVersionError, load_published_content

_REPLY_CODES = frozenset({"ar", "en", "fr"})
_DETECT_CODES = frozenset(SUPPORTED_LANGUAGES)


def frozen_language_policy() -> LanguagePolicy:
    """Schema defaults = frozen system standard (Franco → Arabic, default ar)."""
    return LanguagePolicy()


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


def _normalize_default(value: str | None) -> str:
    code = str(value or "ar").strip().lower()
    return code if code in _REPLY_CODES else "ar"


def resolve_customer_response_language(
    *,
    tenant_id: str | None,
    detected_language: str | None,
    policy: LanguagePolicy | None = None,
) -> str:
    """Map detected inbound language → customer reply language via CM Languages policy."""
    pol = policy if policy is not None else load_language_policy(tenant_id)
    default = _normalize_default(pol.default_language)
    supported = {str(x).strip().lower() for x in (pol.supported_languages or ()) if str(x).strip()}
    if not supported:
        supported = set(SUPPORTED_LANGUAGES)

    detected = str(detected_language or "").strip().lower()
    mapping: dict[str, str] = dict(RESPONSE_LANGUAGE_MAP)
    for key, value in (pol.response_language_map or {}).items():
        k = str(key).strip().lower()
        v = str(value).strip().lower()
        if k:
            mapping[k] = v

    if not detected or detected not in _DETECT_CODES or detected not in supported:
        response = default
    else:
        response = str(mapping.get(detected, default)).strip().lower()

    if response == "franco":
        response = "ar"
    if response not in _REPLY_CODES:
        response = default

    reply_supported = supported & _REPLY_CODES
    if reply_supported and response not in reply_supported:
        response = default if default in reply_supported else sorted(reply_supported)[0]
    return response


def detect_and_resolve_customer_languages(
    *,
    tenant_id: str | None,
    message: str,
    conversation_id: str | None = None,
) -> dict[str, str]:
    """Detect inbound language (no owner/app override) then apply CM Languages policy."""
    from language_resolver import LanguageResolver

    resolver = LanguageResolver()
    cid = (conversation_id or "").strip() or f"cm-lang:{(tenant_id or 'default').strip()}:ephemeral"
    detected = resolver.resolve(
        conversation_id=cid,
        user_text=message or "",
        accept_language=None,
        user_lang_override=None,
    )
    detected_code = str(detected or "").strip().lower() or "ar"
    if detected_code not in _DETECT_CODES:
        detected_code = "ar"
    response = resolve_customer_response_language(tenant_id=tenant_id, detected_language=detected_code)
    return {
        "detected_language": detected_code,
        "response_language": response,
    }


def language_policy_public_summary(tenant_id: str | None) -> dict[str, Any]:
    """Safe summary for Owner Copilot / diagnostics (not a customer override surface)."""
    pol = load_language_policy(tenant_id)
    return {
        "source": "content_manager_languages",
        "supported_languages": list(pol.supported_languages),
        "default_language": _normalize_default(pol.default_language),
        "response_language_map": dict(pol.response_language_map),
        "owner_or_customer_override": False,
        "app_settings_affects_replies": False,
    }
