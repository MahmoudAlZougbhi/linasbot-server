"""Restricted Topics catalog helpers + owner-configured conflict validation."""

from __future__ import annotations

from pathlib import Path

from services.cm.constants import INITIAL_RESTRICTED_LABELS, INITIAL_RESTRICTED_TOPIC_IDS
from services.cm.migration import migrate_legacy_fixture
from services.cm.schemas import RestrictedPolicy, initial_restricted_policy
from services.cm.storage import get_draft, put_draft


def test_initial_restricted_catalog_exists_inactive_by_default() -> None:
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

    inactive = initial_restricted_policy()
    assert all(topic.active is False for topic in inactive.topics)
    assert {topic.id for topic in inactive.topics} == set(INITIAL_RESTRICTED_TOPIC_IDS)

    active = initial_restricted_policy(active=True)
    assert {topic.id for topic in active.topics if topic.active} == set(INITIAL_RESTRICTED_TOPIC_IDS)


def test_migration_does_not_auto_restrict_by_topic_keywords() -> None:
    report = migrate_legacy_fixture(
        source_root=Path("tests/fixtures/cm_migration"),
        tenant_id="cm_restricted_defaults_migration",
    )
    assert report["conflict_count"] == 0
    restricted = get_draft("restricted", tenant_id="cm_restricted_defaults_migration", create_default=True)
    assert list(restricted.payload.get("topics") or []) == []


def test_owner_activated_restricted_topics_still_surface_conflicts() -> None:
    """When the owner explicitly activates Restricted Topics, conflicts remain hard blockers."""
    tenant_id = "cm_restricted_owner_activated"
    migrate_legacy_fixture(source_root=Path("tests/fixtures/cm_migration"), tenant_id=tenant_id)
    env = get_draft("restricted", tenant_id=tenant_id, create_default=True)
    put_draft(
        "restricted",
        payload=initial_restricted_policy(active=True).model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by="test",
    )
    report = migrate_legacy_fixture(source_root=Path("tests/fixtures/cm_migration"), tenant_id=tenant_id)
    codes = {c["code"] for c in report.get("conflicts") or []}
    assert "RESTRICTED_FAQ_AFFIRMATION" in codes or "RESTRICTED_HANDOFF_MATRIX_ROW" in codes
    assert report["conflict_count"] >= 1
    # Policy remains as owner set — migration must not silently clear owner activation.
    policy = RestrictedPolicy.model_validate(get_draft("restricted", tenant_id=tenant_id, create_default=False).payload)
    assert any(t.active for t in policy.topics)
