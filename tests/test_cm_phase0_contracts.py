"""Phase 0/1 contract tests for CM constants and restricted defaults."""

from __future__ import annotations

from services.cm.constants import (
    CM_SECTIONS,
    INITIAL_RESTRICTED_LABELS,
    INITIAL_RESTRICTED_TOPIC_IDS,
    PUBLISH_DISABLED_MESSAGE,
    RESPONSE_LANGUAGE_MAP,
    SUPPORTED_LANGUAGES,
    cm_publish_enabled,
)
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled
from services.cm.schemas import initial_restricted_policy, initial_restricted_topics


def test_supported_languages_contract() -> None:
    assert SUPPORTED_LANGUAGES == ("ar", "en", "fr", "franco")


def test_response_language_map_franco_to_arabic() -> None:
    assert RESPONSE_LANGUAGE_MAP == {
        "ar": "ar",
        "en": "en",
        "fr": "fr",
        "franco": "ar",
    }


def test_cm_sections_include_dynamic_messages_and_restricted() -> None:
    assert "dynamic_messages" in CM_SECTIONS
    assert "restricted" in CM_SECTIONS
    assert "faq" in CM_SECTIONS
    assert "handoff" in CM_SECTIONS
    assert CM_SECTIONS[0] == "ai_basics"


def test_initial_restricted_topic_ids_match_labels() -> None:
    assert INITIAL_RESTRICTED_TOPIC_IDS == (
        "tattoo_removal",
        "co2_laser",
        "pigmentation_removal",
        "facial_skin_cleaning",
    )
    assert set(INITIAL_RESTRICTED_TOPIC_IDS) == set(INITIAL_RESTRICTED_LABELS)
    for _topic_id, labels in INITIAL_RESTRICTED_LABELS.items():
        assert labels["en"]
        assert labels["ar"]
        assert labels["fr"]


def test_initial_restricted_defaults_helpers() -> None:
    topics = initial_restricted_topics()
    assert [t.id for t in topics] == list(INITIAL_RESTRICTED_TOPIC_IDS)
    assert all(t.active for t in topics)
    policy = initial_restricted_policy()
    assert len(policy.topics) == 4
    tattoo = next(t for t in policy.topics if t.id == "tattoo_removal")
    assert tattoo.labels.en == "Tattoo removal"


def test_publish_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CM_PUBLISH_ENABLED", raising=False)
    assert cm_publish_enabled() is False
    assert "saves drafts only" in PUBLISH_DISABLED_MESSAGE
    try:
        ensure_publish_enabled()
        raise AssertionError("expected PublishDisabledError")
    except PublishDisabledError as exc:
        assert str(exc) == PUBLISH_DISABLED_MESSAGE


def test_publish_enabled_when_flag_set(monkeypatch) -> None:
    monkeypatch.setenv("CM_PUBLISH_ENABLED", "true")
    assert cm_publish_enabled() is True
    ensure_publish_enabled()  # does not raise
    monkeypatch.setenv("CM_PUBLISH_ENABLED", "false")
    assert cm_publish_enabled() is False
