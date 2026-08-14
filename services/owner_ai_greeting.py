"""Seeded first assistant bubble for a new owner chat (hardcoded welcome pool)."""

from __future__ import annotations

from typing import Any

from services.owner_ai_account_state import resolve_setup_stage
from services.owner_ai_profile import address_line, normalize_language, read_owner_profile
from services.welcome_pool import pick_welcome

_ADDRESS_PROMPT: dict[str, str] = {
    "en": " How should I address you? 😊",
    "ar": " كيف تفضّل أن أناديك؟ 😊",
    "fr": " Comment souhaitez-vous que je m’adresse à vous ? 😊",
}


def build_greeting(
    *,
    tenant_id: str,
    user_id: str,
    language: str | None = None,
    include_address_prompt: bool = True,
) -> dict[str, Any]:
    from services.owner_ai_onboarding import welcome_chips

    profile = read_owner_profile(user_id)
    lang = normalize_language(language or profile.get("preferred_language"), fallback="en")
    stage = resolve_setup_stage(tenant_id)
    hi = address_line(profile, language=lang)
    text = pick_welcome(language=lang, user_key=user_id, hi=hi)
    asked = bool(profile.get("address_prompt_asked"))
    has_name = bool(profile.get("display_name") or profile.get("form_of_address"))
    if include_address_prompt and not asked and not has_name:
        text += _ADDRESS_PROMPT.get(lang, _ADDRESS_PROMPT["en"])
    return {
        "text": text,
        "setup_stage": stage,
        "language": lang,
        "address_prompt_included": include_address_prompt and not asked and not has_name,
        "gender": profile.get("gender") or "unset",
        "chips": welcome_chips(setup_stage=stage, language=lang),
    }
