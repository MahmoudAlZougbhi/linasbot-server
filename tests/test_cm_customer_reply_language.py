"""Customer reply language follows Content Manager Languages policy."""

from __future__ import annotations

from services.cm.language_policy import frozen_language_policy, resolve_customer_response_language
from services.cm.schemas import LanguagePolicy
from services.owner_ai_context import SYSTEM_PROMPT
from services.owner_copilot_v2.brain_support import SYSTEM_V2


def test_frozen_policy_matches_system_standard() -> None:
    pol = frozen_language_policy()
    assert pol.default_language == "ar"
    assert pol.response_language_map["franco"] == "ar"
    assert resolve_customer_response_language(tenant_id=None, detected_language="franco") == "ar"
    assert resolve_customer_response_language(tenant_id=None, detected_language="en") == "en"
    assert resolve_customer_response_language(tenant_id=None, detected_language="fr") == "fr"


def test_supported_languages_clamp_uses_default() -> None:
    policy = LanguagePolicy(
        supported_languages=("ar", "franco"),
        response_language_map={"ar": "ar", "en": "en", "fr": "fr", "franco": "ar"},
        default_language="ar",
    )
    assert (
        resolve_customer_response_language(
            tenant_id="any",
            detected_language="en",
            policy=policy,
        )
        == "ar"
    )
    assert (
        resolve_customer_response_language(
            tenant_id="any",
            detected_language="franco",
            policy=policy,
        )
        == "ar"
    )


def test_unknown_detected_uses_default_language() -> None:
    policy = LanguagePolicy(
        supported_languages=("en", "fr"),
        response_language_map={"ar": "ar", "en": "en", "fr": "fr", "franco": "ar"},
        default_language="en",
    )
    assert (
        resolve_customer_response_language(
            tenant_id="any",
            detected_language="de",
            policy=policy,
        )
        == "en"
    )


def test_owner_prompts_lock_customer_reply_language_to_cm() -> None:
    for prompt in (SYSTEM_PROMPT, SYSTEM_V2):
        lower = prompt.lower()
        assert "content management" in lower or "languages" in lower
        assert "settings" in lower
        assert "preferred_language" in lower
        assert "dm" in lower or "comment" in lower


def test_answer_luna_messages_include_cm_response_language() -> None:
    from services.customer_reply_v2.answer_luna import build_answer_messages
    from services.customer_reply_v2.models import EvidenceRecord

    msgs = build_answer_messages(
        message="hello",
        fixed_context={"ai_basics": {"advanced_instructions": "x"}, "style": {"style_body": "y"}},
        evidence=[EvidenceRecord("services:s1", "services", "S", "body", "v1")],
        evidence_status="sufficient",
        customer_profile={},
        history_messages=[],
        comment_context=None,
        channel="instagram_dm",
        published_revision="v1",
        response_language="fr",
        detected_language="fr",
    )
    blob = msgs[1]["content"]
    assert "response_language" in blob
    assert "fr" in blob
    assert "Content Manager" in blob or "Languages" in blob
