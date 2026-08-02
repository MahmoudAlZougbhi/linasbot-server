"""Confirm initial Restricted clinic defaults remain the business truth blockers."""

from __future__ import annotations

from services.cm.constants import INITIAL_RESTRICTED_LABELS, INITIAL_RESTRICTED_TOPIC_IDS
from services.cm.schemas import initial_restricted_policy


def test_initial_restricted_topics_match_clinic_business_truth() -> None:
    assert INITIAL_RESTRICTED_TOPIC_IDS == (
        "tattoo_removal",
        "co2_laser",
        "pigmentation_removal",
        "facial_skin_cleaning",
    )
    assert INITIAL_RESTRICTED_LABELS["tattoo_removal"]["en"] == "Tattoo removal"
    assert INITIAL_RESTRICTED_LABELS["co2_laser"]["en"] == "CO2 laser"
    assert INITIAL_RESTRICTED_LABELS["pigmentation_removal"]["en"] == "Pigmentation removal"
    assert INITIAL_RESTRICTED_LABELS["facial_skin_cleaning"]["en"] == "Facial / skin-cleaning sessions"

    policy = initial_restricted_policy()
    active_ids = {topic.id for topic in policy.topics if topic.active}
    assert active_ids == set(INITIAL_RESTRICTED_TOPIC_IDS)
    for topic in policy.topics:
        assert topic.active is True
        assert topic.labels.en
        assert topic.keywords  # used for FAQ/knowledge conflict detection


def test_migration_conflict_codes_surface_restricted_blockers_without_silent_rewrite() -> None:
    """Fixture migration must report Restricted conflicts; it must not auto-resolve them."""
    from pathlib import Path

    from services.cm.migration import migrate_legacy_fixture

    report = migrate_legacy_fixture(
        source_root=Path("tests/fixtures/cm_migration"),
        tenant_id="cm_restricted_defaults_migration",
    )
    codes = {c["code"] for c in report.get("conflicts") or []}
    assert "RESTRICTED_FAQ_AFFIRMATION" in codes or "RESTRICTED_HANDOFF_MATRIX_ROW" in codes
    assert report["conflict_count"] >= 1
