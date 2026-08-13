"""Customer reply language policy — multilingual by default."""

from __future__ import annotations

import json

from services.cm.language_policy import (
    detect_and_resolve_customer_languages,
    ensure_customer_languages,
    frozen_language_policy,
    frozen_response_language_map,
    language_policy_public_summary,
    resolve_customer_response_language,
)
from services.cm.schemas import LanguagePolicy
from services.customer_reply_v2.answer_luna import build_answer_messages, effective_response_language


def test_frozen_policy_defaults() -> None:
    pol = frozen_language_policy()
    assert pol.default_language == "ar"
    assert pol.response_language_map["franco"] == "ar"


def test_english_customer_english_reply() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="en") == "en"


def test_arabic_customer_arabic_reply() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="ar") == "ar"


def test_french_customer_french_reply() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="fr") == "fr"


def test_chinese_customer_chinese_reply() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="zh") == "zh"


def test_arabizi_customer_arabic_script_reply() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="franco") == "ar"


def test_tenant_supported_languages_do_not_force_arabic_replies() -> None:
    policy = LanguagePolicy(
        supported_languages=("ar",),
        response_language_map={"ar": "ar", "en": "en", "fr": "fr", "franco": "ar"},
        default_language="ar",
    )
    assert (
        resolve_customer_response_language(
            tenant_id="tenant-x",
            detected_language="en",
            policy=policy,
        )
        == "en"
    )
    assert (
        resolve_customer_response_language(
            tenant_id="tenant-x",
            detected_language="fr",
            policy=policy,
        )
        == "fr"
    )


def test_unknown_detected_uses_default_language() -> None:
    policy = LanguagePolicy(
        supported_languages=("en", "fr"),
        default_language="en",
    )
    assert (
        resolve_customer_response_language(
            tenant_id="any",
            detected_language="",
            policy=policy,
        )
        == "en"
    )


def test_public_summary_multilingual() -> None:
    summary = language_policy_public_summary(None)
    assert summary["customer_reply_multilingual"] is True
    assert summary["customer_reply_limited_by_supported_languages"] is False
    assert summary["arabizi_reply_policy"] == "understand_only_reply_arabic_script"


def test_effective_response_language_never_arabizi() -> None:
    assert effective_response_language(response_language="franco", fixed_context={}) == "ar"
    assert effective_response_language(response_language="en", fixed_context={}) == "en"


def test_answer_luna_messages_multilingual_rule() -> None:
    from services.customer_reply_v2.models import EvidenceRecord

    msgs = build_answer_messages(
        message="bonjour",
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
    blob = json.dumps(msgs, ensure_ascii=False)
    assert "response_language" in blob
    assert "fr" in blob
    assert "Arabizi" in blob or "Arabic script" in blob


def test_detect_and_resolve_franco() -> None:
    out = detect_and_resolve_customer_languages(
        tenant_id=None,
        message="shu se3er l session",
        conversation_id="test-franco",
    )
    assert out["detected_language"] in {"franco", "ar"}
    assert out["response_language"] == "ar"


def test_ensure_customer_languages_fills_missing() -> None:
    detected, response = ensure_customer_languages(
        tenant_id=None,
        message="Hello, what are your hours?",
        detected_language="",
        response_language="",
        conversation_id="test-ensure",
    )
    assert detected == "en"
    assert response == "en"
