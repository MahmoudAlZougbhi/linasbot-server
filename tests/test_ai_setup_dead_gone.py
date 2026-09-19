"""AI Setup dead islands stay gone; FAQ CRUD lives under services.faq."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE_PATHS = (
    "services/ai_setup/answer_generation.py",
    "services/ai_setup/answer_packet.py",
    "services/ai_setup/off_days.py",
    "services/ai_setup/pricing/audit.py",
    "services/ai_setup/query_interpreter.py",
    "services/ai_setup/response_validator.py",
    "services/ai_setup/runtime_pipeline.py",
    "services/ai_setup/smart_answer_language_catalog.py",
    "services/ai_setup/source_inventory.py",
    "services/ai_setup/tenant_resolve.py",
    "services/ai_setup/voyage_search.py",
    "services/ai_setup/faq_integration.py",
    "services/ai_setup/faq_integration_ops.py",
    "services/ai_setup/faq_integration_helpers.py",
    "services/ai_setup/embeddings.py",
    "services/ai_setup/migration.py",
    "services/ai_setup/prices_catalog_merge.py",
    "services/ai_setup/pricing/catalog_resolve.py",
    "services/ai_setup/pricing/migration.py",
    "services/ai_setup/pricing/migration_extract.py",
    "services/ai_setup/prod_migration.py",
    "services/ai_setup/prod_migration_stage.py",
    "services/ai_setup/redistribution.py",
    "services/ai_setup/scrub_restore.py",
    "services/ai_setup/section_classifier.py",
)

KEEP_PATHS = (
    "services/ai_setup/storage.py",
    "services/ai_setup/save_live.py",
    "services/ai_setup/publish.py",
    "services/ai_setup/durable_flags.py",
    "services/brain/compiler/chunk_apply.py",
    "services/brain/compiler/luna_chunker.py",
    "services/brain/search/index_schedule.py",
    "services/faq/cm_faq.py",
    "services/faq/cm_faq_ops.py",
    "services/faq/cm_faq_helpers.py",
    "modules/cm_api.py",
    "modules/cm_faq_api.py",
    "modules/cm_media_api.py",
    "modules/cm_setup_api.py",
    "modules/flow_api.py",
)


def test_dead_ai_setup_answer_and_search_islands_are_gone() -> None:
    for rel in GONE_PATHS:
        assert not (ROOT / rel).exists(), rel


def test_live_ai_setup_save_publish_luna_voyage_remain() -> None:
    for rel in KEEP_PATHS:
        assert (ROOT / rel).is_file(), rel


def test_cutover_only_ai_setup_tools_are_not_imported_by_live_core() -> None:
    live_roots = (
        ROOT / "services/ai_setup/storage.py",
        ROOT / "services/ai_setup/save_live.py",
        ROOT / "services/ai_setup/publish.py",
        ROOT / "modules/cm_api.py",
        ROOT / "modules/cm_faq_api.py",
        ROOT / "modules/cm_setup_api.py",
        ROOT / "services/brain",
    )
    forbidden = (
        "services.ai_setup.durable_flags",
        "services.ai_setup.embeddings",
        "services.ai_setup.migration",
        "services.ai_setup.prices_catalog_merge",
        "services.ai_setup.pricing.catalog_resolve",
        "services.ai_setup.pricing.migration",
        "services.ai_setup.prod_migration",
        "services.ai_setup.redistribution",
        "services.ai_setup.scrub_restore",
        "services.ai_setup.section_classifier",
        "services.ai_setup.runtime_pipeline",
        "services.ai_setup.voyage_search",
        "services.ai_setup.faq_integration",
    )
    files: list[Path] = []
    for root in live_roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(root.rglob("*.py"))
    for path in files:
        blob = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in blob, f"{path}: {needle}"


def test_put_draft_still_applies_luna_chunks() -> None:
    src = (ROOT / "services/ai_setup/storage.py").read_text(encoding="utf-8")
    assert "apply_save_chunks" in src


def test_publish_still_schedules_brain_voyage_index() -> None:
    src = (ROOT / "services/ai_setup/publish.py").read_text(encoding="utf-8")
    assert "schedule_tenant_index" in src
    assert "services.brain.search.index_schedule" in src
