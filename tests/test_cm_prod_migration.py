"""Production CM migration helpers — restricted scrub + owner-confirmed seeding."""

from __future__ import annotations

from pathlib import Path

from services.cm.prod_migration import (
    run_production_content_migration,
    stage_live_data_for_migration,
)
from services.cm.storage import get_draft


def test_stage_and_migrate_from_flat_sample_data(tmp_path: Path) -> None:
    data_root = tmp_path / "live"
    (data_root / "qa").mkdir(parents=True)
    (data_root / "content").mkdir(parents=True)
    (data_root / "qa" / "qa_pairs.jsonl").write_text(
        '{"question":"What is laser hair removal?","answer":"A light-based hair reduction service.","language":"en","qa_group_id":"g1"}\n'
        '{"question":"Do you offer tattoo removal?","answer":"Yes we offer tattoo removal.","language":"en","qa_group_id":"g_tattoo"}\n',
        encoding="utf-8",
    )
    (data_root / "content" / "price_list.txt").write_text("Use selector price files only.\n", encoding="utf-8")
    (data_root / "content" / "knowledge_base.txt").write_text(
        "Linas Laser provides laser hair removal.\n", encoding="utf-8"
    )
    (data_root / "content" / "style_guide.txt").write_text("Be warm and concise.\n", encoding="utf-8")

    staging = tmp_path / "staging"
    stage = stage_live_data_for_migration(data_root=data_root, staging_root=staging)
    assert any(c["dest"].endswith("qa_pairs.jsonl") for c in stage["copied"])

    report = run_production_content_migration(
        data_root=data_root,
        staging_root=staging,
        tenant_id="cm_prod_mig_test",
        updated_by="test",
    )
    assert report["seeded"]["services"] == ["laser_hair_removal"]
    assert report["scrub"]["faq_removed"]
    assert any(item["qa_group_id"] == "g_tattoo" for item in report["scrub"]["faq_removed"])
    faq = get_draft("faq", tenant_id="cm_prod_mig_test", create_default=True)
    items = list(faq.payload.get("items") or [])
    by_id = {item["qa_group_id"]: item for item in items if isinstance(item, dict)}
    assert "g_tattoo" in by_id
    assert by_id["g_tattoo"].get("status") == "restricted"
    assert "g1" in by_id
    assert by_id["g1"].get("status") != "restricted"
    handoff = get_draft("handoff", tenant_id="cm_prod_mig_test", create_default=True)
    assert all(row.get("topic_id") is None for row in (handoff.payload.get("matrix") or []))
    assert report["conflict_count"] == 0
    assert report["publish_ready"] is True


def test_stage_prefers_nonempty_app_data_over_empty_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    (data_root / "qa").mkdir(parents=True)
    (data_root / "qa" / "qa_pairs.jsonl").write_text("", encoding="utf-8")
    app_data = tmp_path / "app_data"
    app_data.mkdir()
    (app_data / "qa_pairs.jsonl").write_text(
        '{"question":"Hours?","answer":"See published hours.","language":"en","qa_group_id":"g_hours"}\n',
        encoding="utf-8",
    )
    staging = tmp_path / "staging"
    stage = stage_live_data_for_migration(
        data_root=data_root,
        staging_root=staging,
        app_data_root=app_data,
    )
    qa_copied = next(c for c in stage["copied"] if c["dest"].endswith("qa_pairs.jsonl"))
    assert qa_copied["src"].endswith(str(app_data / "qa_pairs.jsonl")) or "app_data" in qa_copied["src"]
    assert (staging / "legacy" / "qa_pairs.jsonl").stat().st_size > 0
