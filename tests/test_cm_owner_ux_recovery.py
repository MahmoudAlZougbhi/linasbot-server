"""Regression coverage for owner-friendly CM UX and restricted index exclusion."""

from __future__ import annotations

from services.ai_setup.schemas import ArticleRecord, FaqRecord, FaqSection, FaqVariant, KnowledgeSection
from tests.cm_semantic_index import _article_entries, _faq_entries


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
