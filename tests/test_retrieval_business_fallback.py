"""DM fallback attaches published knowledge when Luna returns no business files."""

from __future__ import annotations

from types import SimpleNamespace

from services.customer_reply_v2.models import EvidenceRecord, RetrievalResult
from services.customer_reply_v2.retrieval_business_fallback import ensure_dm_business_evidence


def _empty_retrieval() -> RetrievalResult:
    return RetrievalResult(evidence=[], evidence_status="insufficient_final", rounds_used=1)


def test_fallback_skips_honest_insufficient_final() -> None:
    retrieval = _empty_retrieval()
    retrieval.evidence_status = "insufficient_final"
    pointer = SimpleNamespace(content_version_id="pub-1")
    sections = {"knowledge": {"items": [{"id": "k1", "title": "Laser", "body": "CO2"}]}}
    import services.customer_reply_v2.retrieval_business_fallback as fallback

    original = fallback.load_published_content
    fallback.load_published_content = lambda _tenant: (pointer, sections)  # type: ignore[assignment]
    try:
        out = ensure_dm_business_evidence(retrieval, tenant_id="linas", channel="facebook_dm")
        assert out.evidence == []
        assert out.evidence_status == "insufficient_final"
    finally:
        fallback.load_published_content = original


def test_fallback_skips_when_knowledge_already_present() -> None:
    retrieval = _empty_retrieval()
    retrieval.evidence = [
        EvidenceRecord(
            source_id="knowledge:k1",
            section_id="knowledge",
            title="Laser",
            content="CO2 details",
            published_revision="v1",
        )
    ]
    out = ensure_dm_business_evidence(retrieval, tenant_id="linas", channel="facebook_dm")
    assert [item.source_id for item in out.evidence] == ["knowledge:k1"]


def test_fallback_skips_comments_and_missing_publish() -> None:
    retrieval = _empty_retrieval()
    skipped = ensure_dm_business_evidence(retrieval, tenant_id="linas", channel="facebook_comment")
    assert skipped.evidence == []

    def _boom(_tenant: str) -> tuple[object, dict[str, object]]:
        from services.cm.version_store import PublishedVersionError

        raise PublishedVersionError("none")

    import services.customer_reply_v2.retrieval_business_fallback as fallback

    original = fallback.load_published_content
    fallback.load_published_content = _boom  # type: ignore[assignment]
    try:
        out = ensure_dm_business_evidence(_empty_retrieval(), tenant_id="linas", channel="facebook_dm")
        assert out.evidence == []
    finally:
        fallback.load_published_content = original


def test_fallback_injects_published_knowledge() -> None:
    pointer = SimpleNamespace(content_version_id="pub-1")
    sections = {
        "knowledge": {
            "items": [
                {"id": "about-laser", "title": "Laser", "body": "Alexandrite and CO2 are offered."},
            ]
        },
        "services": {"items": [{"id": "hair", "title": "Hair removal", "body": "Full body."}]},
    }

    import services.customer_reply_v2.retrieval_business_fallback as fallback

    original = fallback.load_published_content
    fallback.load_published_content = lambda _tenant: (pointer, sections)  # type: ignore[assignment]
    try:
        empty = _empty_retrieval()
        empty.evidence_status = "insufficient_can_retry"
        out = ensure_dm_business_evidence(empty, tenant_id="linas", channel="facebook_dm")
        ids = [item.source_id for item in out.evidence]
        assert "knowledge:about-laser" in ids
        assert "services:hair" in ids
        assert out.evidence_status == "sufficient"
        assert any("Laser" in item.content for item in out.evidence)
    finally:
        fallback.load_published_content = original
