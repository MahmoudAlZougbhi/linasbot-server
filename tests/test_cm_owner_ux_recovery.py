"""Regression coverage for owner-friendly CM UX and restricted index exclusion."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.schemas import ArticleRecord, CareSection, FaqRecord, FaqSection, FaqVariant, KnowledgeSection
from services.cm.semantic_index import _article_entries, _faq_entries
from services.cm.source_inventory import build_source_inventory


def test_restricted_and_archived_articles_excluded_from_index_entries() -> None:
    knowledge = KnowledgeSection(
        items=[
            ArticleRecord(id="a1", title="Active", body="ok", status="active"),
            ArticleRecord(id="a2", title="Tattoo", body="tattoo removal", status="restricted"),
            ArticleRecord(id="a3", title="Old", body="old", status="archived"),
        ]
    )
    entries = _article_entries(knowledge.model_dump(mode="json"), "knowledge")
    ids = [source_id for source_id, *_ in entries]
    assert ids == ["knowledge:a1"]


def test_restricted_faq_excluded_from_index_entries() -> None:
    faq = FaqSection(
        items=[
            FaqRecord(
                qa_group_id="g1",
                status="active",
                variants=[FaqVariant(language="en", question="hours?", answer="call us")],
            ),
            FaqRecord(
                qa_group_id="g2",
                status="restricted",
                variants=[FaqVariant(language="en", question="tattoo?", answer="we remove tattoos")],
            ),
        ]
    )
    entries = _faq_entries(faq.model_dump(mode="json"))
    assert len(entries) == 1
    assert entries[0][0] == "faq:g1:en"


def test_source_inventory_metadata_only(tmp_path: Path) -> None:
    report = build_source_inventory(tenant_id="linas", data_root=tmp_path)
    assert report["tenant_id"] == "linas"
    assert "article_sources" in report
    assert "staged_legacy_files" in report
    # Ensure we never accidentally dump huge content bodies at top-level keys.
    assert "knowledge_base_text" not in report
    assert "system_prompt" not in report
