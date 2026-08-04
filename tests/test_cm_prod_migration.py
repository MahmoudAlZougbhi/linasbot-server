"""Production CM migration — no keyword scrub; recovered content stays AI-active."""

from __future__ import annotations

import json
from pathlib import Path

from services.cm.prod_migration import (
    run_production_content_migration,
    stage_live_data_for_migration,
)
from services.cm.schemas import ArticleRecord, FaqRecord, FaqVariant, KnowledgeSection
from services.cm.scrub_restore import restore_keyword_scrubbed_content
from services.cm.storage import get_draft, put_draft


def test_stage_and_migrate_keeps_topic_content_active(tmp_path: Path) -> None:
    data_root = tmp_path / "live"
    (data_root / "qa").mkdir(parents=True)
    (data_root / "content" / "knowledge_files").mkdir(parents=True)
    (data_root / "content" / "style_files").mkdir(parents=True)
    (data_root / "settings").mkdir(parents=True)
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
    (data_root / "content" / "system_prompt_template.txt").write_text(
        "You are Linas. Answer only from published facts. Full prompt body retained.\n",
        encoding="utf-8",
    )
    (data_root / "content" / "style_files" / "extra_tone.txt").write_text("Prefer short replies.\n", encoding="utf-8")
    (data_root / "settings" / "dynamic_messages.json").write_text(
        json.dumps(
            {
                "welcome": {"name": "Welcome", "en": "Hello", "ar": "مرحبا", "fr": "Bonjour"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "content" / "knowledge_files" / "about_tattoo.json").write_text(
        json.dumps(
            {
                "id": "about_tattoo",
                "title": "About Tattoo Removal",
                "content": "Tattoo removal uses laser pulses on ink.",
                "tags": ["knowledge"],
                "language": "en",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "content" / "knowledge_files" / "about_co2.json").write_text(
        json.dumps(
            {
                "id": "about_co2",
                "title": "About CO2",
                "content": "CO2 laser resurfacing information.",
                "tags": ["knowledge"],
                "language": "en",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "content" / "knowledge_files" / "about_whitening.json").write_text(
        json.dumps(
            {
                "id": "about_whitening",
                "title": "About Whitening",
                "content": "Whitening and pigmentation information.",
                "tags": ["knowledge"],
                "language": "en",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    staging = tmp_path / "staging"
    stage = stage_live_data_for_migration(data_root=data_root, staging_root=staging)
    assert any(c["dest"].endswith("qa_pairs.jsonl") for c in stage["copied"])
    assert any("style_files" in c["dest"] for c in stage["copied"])
    assert any(c["dest"].endswith("dynamic_messages.json") for c in stage["copied"])

    report = run_production_content_migration(
        data_root=data_root,
        staging_root=staging,
        tenant_id="cm_prod_mig_test",
        updated_by="test",
    )
    assert report["seeded"]["services"] == ["laser_hair_removal"]
    assert report["scrub"]["disabled"] is True
    assert report["scrub"]["faq_removed"] == []
    assert report["seeded"]["dynamic_messages"]["imported"] >= 1
    assert "extra_tone.txt" in report["seeded"]["style"]["style_files"]
    assert int(report["seeded"]["ai_basics"]["prompt_chars"]) > 40

    faq = get_draft("faq", tenant_id="cm_prod_mig_test", create_default=True)
    items = list(faq.payload.get("items") or [])
    by_id = {item["qa_group_id"]: item for item in items if isinstance(item, dict)}
    assert "g_tattoo" in by_id
    assert by_id["g_tattoo"].get("status") == "active"
    assert "g1" in by_id
    assert by_id["g1"].get("status") == "active"

    knowledge = KnowledgeSection.model_validate(
        get_draft("knowledge", tenant_id="cm_prod_mig_test", create_default=True).payload
    )
    titles = {item.title for item in knowledge.items}
    assert "About Tattoo Removal" in titles
    assert "About CO2" in titles
    assert "About Whitening" in titles
    assert all(item.status == "active" for item in knowledge.items if item.title.startswith("About "))

    dyn = get_draft("dynamic_messages", tenant_id="cm_prod_mig_test", create_default=True)
    dyn_items = list(dyn.payload.get("items") or [])
    assert any(item.get("id") == "welcome" for item in dyn_items if isinstance(item, dict))

    ai = get_draft("ai_basics", tenant_id="cm_prod_mig_test", create_default=True)
    instructions = str(ai.payload.get("advanced_instructions") or "")
    assert "Full prompt body retained" in instructions
    assert "Never offer tattoo removal" not in instructions

    restricted = get_draft("restricted", tenant_id="cm_prod_mig_test", create_default=True)
    assert list(restricted.payload.get("topics") or []) == []

    handoff = get_draft("handoff", tenant_id="cm_prod_mig_test", create_default=True)
    assert all(row.get("topic_id") is None for row in (handoff.payload.get("matrix") or []))
    assert report["conflict_count"] == 0
    assert report["publish_ready"] is True


def test_restore_reactivates_keyword_scrubbed_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    tenant_id = "cm_restore_scrub_test"
    put_draft(
        "faq",
        payload={
            "items": [
                FaqRecord(
                    qa_group_id="g_tattoo",
                    variants=[FaqVariant(language="en", question="tattoo?", answer="yes")],
                    status="restricted",
                    tags=["restricted_scrub", "topic:tattoo_removal"],
                    notes="[restricted] Not used by AI — topic=tattoo_removal",
                ).model_dump(mode="json")
            ]
        },
        if_match=get_draft("faq", tenant_id=tenant_id, create_default=True).etag,
        tenant_id=tenant_id,
        updated_by="test",
    )
    put_draft(
        "knowledge",
        payload={
            "items": [
                ArticleRecord(
                    id="k_tattoo",
                    title="About Tattoo Removal",
                    body="info",
                    status="restricted",
                    tags=["restricted_scrub", "topic:tattoo_removal"],
                ).model_dump(mode="json")
            ]
        },
        if_match=get_draft("knowledge", tenant_id=tenant_id, create_default=True).etag,
        tenant_id=tenant_id,
        updated_by="test",
    )
    report = restore_keyword_scrubbed_content(tenant_id=tenant_id, updated_by="test")
    assert "g_tattoo" in report["faq_restored_ids"]
    assert "k_tattoo" in report["knowledge_restored_ids"]
    faq = get_draft("faq", tenant_id=tenant_id, create_default=True)
    assert faq.payload["items"][0]["status"] == "active"
    knowledge = get_draft("knowledge", tenant_id=tenant_id, create_default=True)
    assert knowledge.payload["items"][0]["status"] == "active"


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
