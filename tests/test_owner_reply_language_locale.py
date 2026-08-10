"""Owner Copilot reply language follows the user's latest message (not app locale)."""

from __future__ import annotations

from services.owner_ai_context import pack_owner_turn_context
from services.owner_ai_onboarding import welcome_chips
from services.owner_ai_profile import (
    coerce_language,
    detect_owner_message_language,
    language_from_accept_header,
    resolve_owner_reply_language,
)


def test_coerce_and_accept_language() -> None:
    assert coerce_language("ar-LB") == "ar"
    assert coerce_language("fr-FR") == "fr"
    assert coerce_language("en-US") == "en"
    assert coerce_language("xx") is None
    assert language_from_accept_header("ar-LB,ar;q=0.9,en;q=0.8") == "ar"
    assert language_from_accept_header("fr,en;q=0.8") == "fr"
    assert language_from_accept_header(None) is None


def test_detect_owner_message_language() -> None:
    assert detect_owner_message_language("مرحبا كيفك") == "ar"
    assert detect_owner_message_language("kifak shu akhbarak") == "ar"
    assert detect_owner_message_language("Bonjour, merci pour l'aide") == "fr"
    assert detect_owner_message_language("Please check my subscription") == "en"
    assert detect_owner_message_language("🙂") is None


def test_resolve_follows_user_not_app_locale() -> None:
    # App English, user Arabic → Arabic reply
    assert (
        resolve_owner_reply_language(
            "شو وضع الاشتراك؟",
            reply_language_override="en",
            preferred_language="en",
        )
        == "ar"
    )
    # App Arabic, user English → English reply
    assert (
        resolve_owner_reply_language(
            "What can Linas do for my clinic?",
            reply_language_override="ar",
            preferred_language="ar",
        )
        == "en"
    )
    # Unclear → app/preferred fallback
    assert (
        resolve_owner_reply_language(
            "🙂",
            reply_language_override="fr",
            preferred_language="en",
        )
        == "fr"
    )


def test_welcome_chips_localized_labels() -> None:
    ar = welcome_chips(setup_stage="new", language="ar")
    fr = welcome_chips(setup_stage="new", language="fr")
    learn_ar = next(c for c in ar if c["id"] == "learn_app")
    learn_fr = next(c for c in fr if c["id"] == "learn_app")
    assert "حابب" in learn_ar["label"] or "التطبيق" in learn_ar["label"]
    assert "app" in learn_fr["label"].lower() or "savoir" in learn_fr["label"].lower()
    # Tool prompts stay English for reliable tool calling.
    assert "Owner Copilot" in learn_ar["prompt"] or "Linas AI" in learn_ar["prompt"]


def test_pack_owner_turn_follows_user_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.owner_ai_context.build_account_summary",
        lambda **_kwargs: {
            "setup_stage": "new",
            "cm": {},
            "integrations": {},
            "plan": {},
            "wallet": {},
            "profile": {
                "display_name": "Owner",
                "gender": "unset",
                "preferred_language": "en",
                "form_of_address": None,
            },
        },
    )
    monkeypatch.setattr("services.owner_ai_context.retrieve_capabilities", lambda *_a, **_k: [])
    # Free Arabic typing with English app locale → Arabic
    ctx = pack_owner_turn_context(
        tenant_id="t1",
        user_id="u1",
        user_text="شرح لي كيف بشتغل التطبيق",
        messages=[],
        reply_language="en",
    )
    assert ctx["reply_language"] == "ar"
    # Free English typing with Arabic preferred → English
    ctx_en = pack_owner_turn_context(
        tenant_id="t1",
        user_id="u1",
        user_text="Explain my Meta connection status",
        messages=[],
        reply_language="ar",
    )
    assert ctx_en["reply_language"] == "en"


def test_pack_owner_turn_welcome_chip_uses_app_locale(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.owner_ai_context.build_account_summary",
        lambda **_kwargs: {
            "setup_stage": "new",
            "cm": {},
            "integrations": {},
            "plan": {},
            "wallet": {},
            "profile": {
                "display_name": "Owner",
                "gender": "unset",
                "preferred_language": "ar",
                "form_of_address": None,
            },
        },
    )
    monkeypatch.setattr("services.owner_ai_context.retrieve_capabilities", lambda *_a, **_k: [])
    chip = next(c for c in welcome_chips(setup_stage="new", language="ar") if c["id"] == "learn_app")
    ctx = pack_owner_turn_context(
        tenant_id="t1",
        user_id="u1",
        user_text=chip["prompt"],  # English tool prompt
        messages=[],
        reply_language="ar",
    )
    assert ctx["reply_language"] == "ar"
