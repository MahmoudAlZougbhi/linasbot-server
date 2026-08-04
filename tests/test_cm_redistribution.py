"""CM section redistribution — classification, idempotency, no topic scrub."""

from __future__ import annotations

import json
from pathlib import Path

from services.cm.prod_migration import run_production_content_migration
from services.cm.redistribution import redistribute_knowledge_draft, section_counts_snapshot
from services.cm.schemas import KnowledgeSection, ServicesSection
from services.cm.section_classifier import classify_article, detect_service_availability_conflicts
from services.cm.storage import get_draft


def test_classifier_routes_known_misplaced_titles() -> None:
    cases = [
        ("<LOCATION_RULES>", "Beirut and Antelias branches with hours.", ["branches"]),
        ("</APPOINTMENT_RULES>", "Booking and appointment management rules.", ["handoff"]),
        ("## Greeting Rule", "Greet the customer warmly on first message.", ["ai_basics", "dynamic_messages"]),
        ("## New User Handling Rules", "How to handle new users.", ["ai_basics", "dynamic_messages"]),
        ("Beard Area Pricing and Rule", "Beard area pricing notes without inventing amounts.", ["prices"]),
        (
            "</Tattoo_Removal_Training_Philosophy>",
            "Tattoo removal training philosophy. We offer tattoo removal.",
            ["services", "knowledge"],
        ),
        (
            "</CO2_Laser_Training_Philosophy>",
            "CO2 laser training philosophy for offered resurfacing.",
            ["services", "knowledge"],
        ),
        (
            "</DPL_Whitening_Training_Philosophy>",
            "DPL whitening training philosophy.",
            ["services", "knowledge"],
        ),
        (
            "</Laser_Hair_Removal_Training_Philosophy_For_Men_And_Women>",
            "Laser hair removal training philosophy for men and women.",
            ["services", "knowledge"],
        ),
        (
            "Shave before laser",
            "Customers should shave before the session. Aftercare tips.",
            ["care"],
        ),
        ("Legacy knowledge base", "General clinic education about Linas Laser.", ["knowledge"]),
    ]
    for title, body, expected in cases:
        result = classify_article(article_id="x", title=title, body=body)
        assert result.targets == expected, (title, result.targets, result.rationale)


def test_classifier_never_marks_restricted_by_topic_name() -> None:
    result = classify_article(
        article_id="t",
        title="</Tattoo_Removal_Training_Philosophy>",
        body="Tattoo removal is offered. CO2 and DPL whitening guidance included.",
    )
    assert "restricted" not in result.targets
    assert result.keep_in_knowledge_active is True
    assert any(s.id == "tattoo_removal" and s.available for s in result.service_derivations)


def test_educational_without_availability_stays_knowledge_only() -> None:
    result = classify_article(
        article_id="edu",
        title="About Tattoo Removal",
        body="Tattoo removal uses laser pulses on ink. Educational overview only.",
    )
    assert result.targets == ["knowledge"]
    assert result.service_derivations == []


def test_availability_conflict_is_surfaced() -> None:
    a = classify_article(
        article_id="a",
        title="Tattoo offered",
        body="We offer tattoo removal.",
    )
    b = classify_article(
        article_id="b",
        title="Tattoo not offered",
        body="We do not offer tattoo removal.",
    )
    conflicts = detect_service_availability_conflicts([a, b])
    assert any(c["service_id"] == "tattoo_removal" for c in conflicts)


def test_redistribution_idempotent_and_preserves_checksums(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    data_root = tmp_path / "live"
    (data_root / "qa").mkdir(parents=True)
    (data_root / "content" / "knowledge_files").mkdir(parents=True)
    (data_root / "settings").mkdir(parents=True)
    (data_root / "qa" / "qa_pairs.jsonl").write_text(
        '{"question":"Laser?","answer":"Yes.","language":"en","qa_group_id":"g1"}\n',
        encoding="utf-8",
    )
    (data_root / "content" / "knowledge_base.txt").write_text("Linas Laser clinic education.\n", encoding="utf-8")
    (data_root / "content" / "price_list.txt").write_text("See catalog.\n", encoding="utf-8")
    (data_root / "content" / "style_guide.txt").write_text("Warm tone.\n", encoding="utf-8")
    (data_root / "content" / "system_prompt_template.txt").write_text("You are Linas.\n", encoding="utf-8")
    (data_root / "settings" / "dynamic_messages.json").write_text("{}", encoding="utf-8")

    files = {
        "loc.json": {
            "id": "loc",
            "title": "<LOCATION_RULES>",
            "content": "Beirut and Antelias location rules.",
            "checksum": "sha_loc",
        },
        "appt.json": {
            "id": "appt",
            "title": "</APPOINTMENT_RULES>",
            "content": "Appointment booking rules and handoff.",
            "checksum": "sha_appt",
        },
        "greet.json": {
            "id": "greet",
            "title": "## Greeting Rule",
            "content": "Greeting rule for first message.",
            "checksum": "sha_greet",
        },
        "tattoo.json": {
            "id": "tattoo",
            "title": "</Tattoo_Removal_Training_Philosophy>",
            "content": "Tattoo removal training philosophy. We offer tattoo removal.",
            "checksum": "sha_tattoo",
        },
        "price.json": {
            "id": "beard_price",
            "title": "Beard Area Pricing and Rule",
            "content": "Beard area pricing notes.",
            "checksum": "sha_price",
        },
        "prep.json": {
            "id": "prep",
            "title": "Laser prep",
            "content": "Shave before laser hair removal session.",
            "tags": ["prep"],
            "checksum": "sha_prep",
        },
    }
    for name, payload in files.items():
        (data_root / "content" / "knowledge_files" / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")

    staging = tmp_path / "staging"
    tenant = "cm_redistrib_test"
    report = run_production_content_migration(
        data_root=data_root,
        staging_root=staging,
        tenant_id=tenant,
        updated_by="test",
    )
    assert report["scrub"]["disabled"] is True
    assert list(get_draft("restricted", tenant_id=tenant).payload.get("topics") or []) == []

    first = report["redistribution"]
    second = redistribute_knowledge_draft(tenant_id=tenant, updated_by="test")
    assert first["mapped"] == second["mapped"]
    assert first["services_count"] == second["services_count"]

    knowledge = KnowledgeSection.model_validate(get_draft("knowledge", tenant_id=tenant).payload)
    active_titles = {i.title for i in knowledge.items if i.status == "active"}
    archived_titles = {i.title for i in knowledge.items if i.status == "archived"}
    assert "</Tattoo_Removal_Training_Philosophy>" in active_titles
    assert "<LOCATION_RULES>" in archived_titles
    assert "</APPOINTMENT_RULES>" in archived_titles
    assert "## Greeting Rule" in archived_titles
    assert "Beard Area Pricing and Rule" in archived_titles

    services = ServicesSection.model_validate(get_draft("services", tenant_id=tenant).payload)
    service_ids = {s.id for s in services.items}
    assert "laser_hair_removal" in service_ids
    assert "tattoo_removal" in service_ids
    tattoo = next(s for s in services.items if s.id == "tattoo_removal")
    assert tattoo.available is True

    handoff = get_draft("handoff", tenant_id=tenant).payload
    assert "Appointment booking rules" in str(handoff.get("notes") or "")
    branches = get_draft("branches", tenant_id=tenant).payload
    assert "Beirut and Antelias" in str(branches.get("notes") or "")
    ai = get_draft("ai_basics", tenant_id=tenant).payload
    assert "Greeting rule" in str(ai.get("greeting_behavior") or "")
    prices = get_draft("prices", tenant_id=tenant).payload
    assert "Beard area pricing" in str(prices.get("notes") or "")

    from services.cm.schemas import CareSection

    care = CareSection.model_validate(get_draft("care", tenant_id=tenant).payload)
    checksums = {i.source_checksum for i in knowledge.items if i.source_checksum}
    checksums |= {i.source_checksum for i in care.items if i.source_checksum}
    assert {"sha_loc", "sha_appt", "sha_greet", "sha_tattoo", "sha_price", "sha_prep"} <= checksums
    assert "sha_loc" in (first.get("checksums") or [])
    assert any(i.title == "Laser prep" for i in care.items)

    # Re-run must not duplicate notes blocks.
    notes1 = str(handoff.get("notes") or "")
    notes2 = str(get_draft("handoff", tenant_id=tenant).payload.get("notes") or "")
    assert notes1.count("id=") == notes2.count("id=")

    before = section_counts_snapshot(tenant_id=tenant)
    redistribute_knowledge_draft(tenant_id=tenant, updated_by="test")
    after = section_counts_snapshot(tenant_id=tenant)
    assert before == after
