"""Customer reply language policy — multilingual by default."""

from __future__ import annotations

from services.cm.language_policy import (
    detect_and_resolve_customer_languages,
    ensure_customer_languages,
    frozen_language_policy,
    language_policy_public_summary,
    resolve_customer_response_language,
)
from services.cm.schemas import LanguagePolicy


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


def test_unknown_detected_uses_system_default_not_tenant() -> None:
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
        == "ar"
    )


def test_public_summary_multilingual() -> None:
    summary = language_policy_public_summary(None)
    assert summary["source"] == "system_global"
    assert summary["editable"] == []
    assert summary["owner_or_customer_override"] is False
    assert summary["customer_reply_multilingual"] is True
    assert summary["customer_reply_limited_by_supported_languages"] is False
    assert summary["arabizi_reply_policy"] == "understand_only_reply_arabic_script"


def test_effective_response_language_never_arabizi() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="franco") == "ar"
    assert resolve_customer_response_language(tenant_id=None, detected_language="en") == "en"


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
