"""CM Phase 4 migration: fixture copy-in, idempotency, restricted conflict flagging."""

from __future__ import annotations

from pathlib import Path

from services.cm.migration import migrate_legacy_fixture
from services.cm.paths import archive_dir
from services.cm.schemas import FaqSection, HandoffPolicy, KnowledgeSection
from services.cm.storage import get_draft

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "cm_migration"


def test_migration_imports_faq_knowledge_and_handoff() -> None:
    tenant_id = "cm_migration_test_basic"
    report = migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)

    assert report["tenant_id"] == tenant_id
    assert report["faq_groups_imported"] == 3  # 3 rows in fixture qa_pairs.jsonl, no shared group ids
    assert report["knowledge_articles_imported"] >= 2  # legacy knowledge_base.txt + price_list.txt
    assert report["handoff_contacts_imported"] == 4  # laser branch/gender contacts only (no tattoo)

    faq_env = get_draft("faq", tenant_id=tenant_id)
    faq_section = FaqSection.model_validate(faq_env.payload)
    assert len(faq_section.items) == 3
    assert all("legacy_migration" in item.tags for item in faq_section.items)


def test_migration_routes_prep_knowledge_file_into_care_section() -> None:
    tenant_id = "cm_migration_test_care_routing"
    migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)

    from services.cm.schemas import CareSection

    care_env = get_draft("care", tenant_id=tenant_id)
    care_section = CareSection.model_validate(care_env.payload)
    assert any(item.id.startswith("legacy_") and "prep" in item.tags for item in care_section.items)

    knowledge_env = get_draft("knowledge", tenant_id=tenant_id)
    knowledge_section = KnowledgeSection.model_validate(knowledge_env.payload)
    # sample_prep.json must NOT also appear duplicated under knowledge.
    assert not any("Laser prep" == item.title for item in knowledge_section.items)


def test_migration_does_not_auto_flag_tattoo_content_as_restricted() -> None:
    """Recovered tattoo FAQ/knowledge stays active unless the owner configures Restricted Topics."""
    tenant_id = "cm_migration_test_conflict"
    report = migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)

    assert report["conflict_count"] == 0
    faq_env = get_draft("faq", tenant_id=tenant_id)
    faq_section = FaqSection.model_validate(faq_env.payload)
    tattoo_items = [
        item
        for item in faq_section.items
        if any(
            any(marker in f"{v.question} {v.answer}".lower() for marker in ("tattoo", "وشم", "تاتو"))
            for v in item.variants
        )
    ]
    assert tattoo_items
    assert all(item.status == "active" for item in tattoo_items)


def test_owner_restricted_policy_flags_tattoo_conflict() -> None:
    from services.cm.schemas import initial_restricted_policy
    from services.cm.storage import put_draft

    tenant_id = "cm_migration_test_owner_restricted"
    migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)
    env = get_draft("restricted", tenant_id=tenant_id, create_default=True)
    put_draft(
        "restricted",
        payload=initial_restricted_policy(active=True).model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by="test",
    )
    report = migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)
    assert report["conflict_count"] >= 1
    codes = {c["code"] for c in report["conflicts"]}
    assert "RESTRICTED_FAQ_AFFIRMATION" in codes


def test_migration_is_idempotent() -> None:
    tenant_id = "cm_migration_test_idempotent"
    first = migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)
    second = migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)

    assert first["faq_groups_imported"] == second["faq_groups_imported"]
    assert first["knowledge_articles_imported"] == second["knowledge_articles_imported"]
    assert first["handoff_contacts_imported"] == second["handoff_contacts_imported"]
    assert first["conflict_count"] == second["conflict_count"]

    faq_env = get_draft("faq", tenant_id=tenant_id)
    faq_section = FaqSection.model_validate(faq_env.payload)
    # Deterministic ids: re-running must not duplicate groups.
    assert len(faq_section.items) == len({item.qa_group_id for item in faq_section.items})
    assert len(faq_section.items) == 3

    handoff_env = get_draft("handoff", tenant_id=tenant_id)
    handoff_policy = HandoffPolicy.model_validate(handoff_env.payload)
    assert len(handoff_policy.contacts) == len({c.id for c in handoff_policy.contacts})
    assert len(handoff_policy.contacts) == 4


def test_migration_archives_legacy_files_under_tenant_cm_archive() -> None:
    tenant_id = "cm_migration_test_archive"
    report = migrate_legacy_fixture(source_root=FIXTURE_ROOT, tenant_id=tenant_id)

    assert (
        len(report["archived_files"]) == 4
    )  # price_list.txt, knowledge_base.txt, qa_pairs.jsonl, knowledge_files/*.json
    root = archive_dir(tenant_id) / "legacy_migration"
    for entry in report["archived_files"]:
        archived_path = Path(entry["archived_path"])
        assert archived_path.exists()
        assert str(archived_path).startswith(str(root))
        assert archived_path.read_bytes() and entry["sha256"]


def test_migration_missing_source_raises() -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        migrate_legacy_fixture(source_root="/nonexistent/path/for/sure", tenant_id="cm_migration_test_missing")
