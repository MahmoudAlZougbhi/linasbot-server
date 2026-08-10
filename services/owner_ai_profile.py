"""Owner profile preferences for System Copilot (never infer gender from name/email)."""

from __future__ import annotations

import re
from typing import Any, Literal

GenderValue = Literal["male", "female", "unset"]
LangValue = Literal["ar", "en", "fr"]

ALLOWED_GENDERS: frozenset[str] = frozenset({"male", "female", "unset"})
ALLOWED_LANGS: frozenset[str] = frozenset({"ar", "en", "fr"})

_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")
# Safer Franco / Arabizi markers (avoid single-digit false positives like "3"/"7").
_FRANCO_WORD_MARKERS = (
    "kifak",
    "kifik",
    "kif",
    "shou",
    "shu",
    "mish",
    "mesh",
    "mafi",
    "bade",
    "baddi",
    "ehke",
    "a7ke",
    "mar7aba",
    "ahla",
    "yalá",
    "yalla",
    "keef",
    "shu badek",
    "shou badek",
)
_FRENCH_MARKERS = (
    "bonjour",
    "bonsoir",
    "merci",
    "salut",
    "s'il",
    "s’il",
    "vous",
    "abonnement",
    "utilisation",
    "je veux",
    "je suis",
    "comment ça",
    "comment ca",
)


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


def coerce_language(value: Any) -> LangValue | None:
    """Return ar/en/fr when recognizable; otherwise None (no fallback)."""
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("fr"):
        return "fr"
    if raw.startswith("en"):
        return "en"
    return None


def language_from_accept_header(header: str | None) -> LangValue | None:
    """Parse first tag from Accept-Language (e.g. 'ar-LB,ar;q=0.9')."""
    if not header:
        return None
    first = header.split(",", 1)[0].strip().split(";", 1)[0].strip()
    return coerce_language(first)


def detect_owner_message_language(text: str) -> LangValue | None:
    """Detect reply language from the latest owner/guest message.

    Franco / Arabizi → ``ar`` (reply in Arabic script). Returns None when unclear.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if _ARABIC_SCRIPT.search(raw):
        return "ar"
    lower = raw.lower()
    if any(marker in lower for marker in _FRANCO_WORD_MARKERS):
        return "ar"
    if any(marker in lower for marker in _FRENCH_MARKERS):
        return "fr"
    # Substantial Latin text without AR/FR/Franco markers → English.
    letters = sum(1 for ch in raw if ch.isalpha())
    if letters >= 3:
        return "en"
    return None


def resolve_owner_reply_language(
    user_text: str,
    *,
    reply_language_override: str | None = None,
    preferred_language: str | None = None,
    treat_as_ui_prompt: bool = False,
) -> LangValue:
    """Owner Copilot reply language: follow the user's latest message.

    App / preferred locale is only for welcome-chip / UI prompts and unclear detection.
    Never used to lock customer DM/comment language (CM Languages owns that).
    """
    fallback = coerce_language(reply_language_override) or normalize_language(preferred_language, fallback="en")
    if treat_as_ui_prompt:
        return fallback
    detected = detect_owner_message_language(user_text)
    if detected:
        return detected
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
