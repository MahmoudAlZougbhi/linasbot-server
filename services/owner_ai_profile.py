"""Owner profile preferences for System Copilot (never infer gender from name/email)."""

from __future__ import annotations

from typing import Any, Literal

GenderValue = Literal["male", "female", "unset"]
LangValue = Literal["ar", "en", "fr"]

ALLOWED_GENDERS: frozenset[str] = frozenset({"male", "female", "unset"})
ALLOWED_LANGS: frozenset[str] = frozenset({"ar", "en", "fr"})


def normalize_gender(value: Any) -> GenderValue:
    raw = str(value or "").strip().lower()
    if raw in {"male", "m", "man"}:
        return "male"
    if raw in {"female", "f", "woman"}:
        return "female"
    return "unset"


def normalize_language(value: Any, *, fallback: LangValue = "en") -> LangValue:
    raw = str(value or "").strip().lower()
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("fr"):
        return "fr"
    if raw.startswith("en"):
        return "en"
    return fallback


def never_infer_gender_from_identity(*, email: str | None = None, name: str | None = None) -> GenderValue:
    """Explicit contract: identity strings must not produce a gender guess."""
    del email, name
    return "unset"


def read_owner_profile(user_id: str) -> dict[str, Any]:
    from services.user_service import user_service

    user = user_service.get_user_by_id(user_id) or {}
    gender = normalize_gender(user.get("gender"))
    # Defense: if somehow stored from a bad client, still do not invent from email/name.
    if gender not in ALLOWED_GENDERS:
        gender = never_infer_gender_from_identity(
            email=str(user.get("email") or ""),
            name=str(user.get("name") or ""),
        )
    display_name = str(user.get("displayName") or user.get("name") or "").strip()
    preferred_language = normalize_language(user.get("preferredLanguage"), fallback="en")
    form = str(user.get("formOfAddress") or "").strip()
    return {
        "user_id": user_id,
        "email": user.get("email"),
        "display_name": display_name or None,
        "gender": gender,
        "preferred_language": preferred_language,
        "form_of_address": form or None,
        "address_prompt_asked": bool(user.get("addressPromptAsked")),
        "business_name": user.get("businessName"),
        "role": user.get("role"),
        "tenant_id": user.get("tenantId"),
    }


def update_owner_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Persist optional gender / display / language / form-of-address. No inference."""
    from services.user_service import user_service

    payload: dict[str, Any] = {}
    if "gender" in updates and updates["gender"] is not None:
        g = normalize_gender(updates["gender"])
        payload["gender"] = g
    if "display_name" in updates or "displayName" in updates:
        name = updates.get("display_name", updates.get("displayName"))
        if name is not None:
            cleaned = str(name).strip()[:80]
            payload["displayName"] = cleaned
            # Keep legacy name aligned for dashboards that still read `name`.
            if cleaned:
                payload["name"] = cleaned
    if "preferred_language" in updates or "preferredLanguage" in updates:
        lang = updates.get("preferred_language", updates.get("preferredLanguage"))
        if lang is not None:
            payload["preferredLanguage"] = normalize_language(lang)
    if "form_of_address" in updates or "formOfAddress" in updates:
        form = updates.get("form_of_address", updates.get("formOfAddress"))
        if form is not None:
            payload["formOfAddress"] = str(form).strip()[:80]
    if "address_prompt_asked" in updates or "addressPromptAsked" in updates:
        flag = updates.get("address_prompt_asked", updates.get("addressPromptAsked"))
        payload["addressPromptAsked"] = bool(flag)

    if not payload:
        return read_owner_profile(user_id)
    user_service.update_user(user_id, payload)
    return read_owner_profile(user_id)


def address_line(profile: dict[str, Any], *, language: str) -> str:
    """Neutral if gender unset — never invent Mr/Ms from email."""
    form = str(profile.get("form_of_address") or "").strip()
    display = str(profile.get("display_name") or "").strip()
    gender = normalize_gender(profile.get("gender"))
    name = form or display
    if not name:
        if language == "ar":
            return "مرحباً"
        if language == "fr":
            return "Bonjour"
        return "Hello"
    if gender == "male":
        if language == "ar":
            return f"مرحباً {name}"
        if language == "fr":
            return f"Bonjour {name}"
        return f"Hello {name}"
    if gender == "female":
        if language == "ar":
            return f"مرحباً {name}"
        if language == "fr":
            return f"Bonjour {name}"
        return f"Hello {name}"
    # unset — neutral, no gendered title
    if language == "ar":
        return f"مرحباً {name}"
    if language == "fr":
        return f"Bonjour {name}"
    return f"Hello {name}"
