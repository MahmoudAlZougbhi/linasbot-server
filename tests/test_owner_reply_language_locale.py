"""Owner Copilot reply language follows app/preferred locale, not English chip prompts."""

from __future__ import annotations

from services.owner_ai_context import pack_owner_turn_context
from services.owner_ai_onboarding import welcome_chips
from services.owner_ai_profile import coerce_language, language_from_accept_header


def test_coerce_and_accept_language() -> None:
    assert coerce_language("ar-LB") == "ar"
    assert coerce_language("fr-FR") == "fr"
    assert coerce_language("en-US") == "en"
    assert coerce_language("xx") is None
    assert language_from_accept_header("ar-LB,ar;q=0.9,en;q=0.8") == "ar"
    assert language_from_accept_header("fr,en;q=0.8") == "fr"
    assert language_from_accept_header(None) is None


def test_welcome_chips_localized_labels() -> None:
    ar = welcome_chips(setup_stage="new", language="ar")
    fr = welcome_chips(setup_stage="new", language="fr")
    learn_ar = next(c for c in ar if c["id"] == "learn_app")
    learn_fr = next(c for c in fr if c["id"] == "learn_app")
    assert "حابب" in learn_ar["label"] or "التطبيق" in learn_ar["label"]
    assert "app" in learn_fr["label"].lower() or "savoir" in learn_fr["label"].lower()
    # Tool prompts stay English for reliable tool calling.
    assert "Owner Copilot" in learn_ar["prompt"] or "Linas AI" in learn_ar["prompt"]


def test_pack_owner_turn_prefers_app_locale_over_english_chip_text(monkeypatch) -> None:
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
    ctx = pack_owner_turn_context(
        tenant_id="t1",
        user_id="u1",
        user_text="Want to learn more about the app?",  # English chip prompt
        messages=[],
    )
    assert ctx["reply_language"] == "ar"
    ctx_fr = pack_owner_turn_context(
        tenant_id="t1",
        user_id="u1",
        user_text="Check my subscription",
        messages=[],
        reply_language="fr",
    )
    assert ctx_fr["reply_language"] == "fr"
