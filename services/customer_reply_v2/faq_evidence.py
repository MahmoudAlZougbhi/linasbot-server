"""FAQ match payloads for Luna/Tera when direct reply is not eligible."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.models import EvidenceRecord, RetrievalResult


def faq_candidate_payload(metadata: dict[str, Any] | None, *, answer: str = "", question: str = "") -> dict[str, Any]:
    meta = dict(metadata or {})
    return {
        "faq_id": meta.get("faq_id") or meta.get("source_id") or "",
        "faq_revision": meta.get("faq_revision") or meta.get("published_revision") or "",
        "match_type": meta.get("match_type") or meta.get("tier") or "",
        "match_score": meta.get("match_score"),
        "question": question or meta.get("question") or "",
        "answer": answer or meta.get("answer") or "",
        "language": meta.get("matched_language") or meta.get("language") or "",
        "direct_eligible": False,
    }


def faq_evidence_record(candidate: dict[str, Any], *, published_revision: str = "") -> EvidenceRecord | None:
    faq_id = str(candidate.get("faq_id") or "").strip()
    answer = str(candidate.get("answer") or "").strip()
    if not faq_id or not answer:
        return None
    question = str(candidate.get("question") or "").strip()
    body = f"Q: {question}\nA: {answer}" if question else answer
    return EvidenceRecord(
        source_id=f"faq:{faq_id}",
        section_id="faq",
        title=question or faq_id,
        content=body,
        published_revision=str(candidate.get("faq_revision") or published_revision or ""),
    )


def merge_faq_evidence(retrieval: RetrievalResult, candidates: list[dict[str, Any]]) -> RetrievalResult:
    existing = {e.source_id for e in retrieval.evidence}
    extra: list[EvidenceRecord] = []
    for cand in candidates:
        record = faq_evidence_record(cand, published_revision="")
        if record is None or record.source_id in existing:
            continue
        extra.append(record)
        existing.add(record.source_id)
    if not extra:
        return retrieval
    retrieval.evidence = extra + list(retrieval.evidence)
    for rec in extra:
        if rec.source_id not in retrieval.selected_source_ids:
            retrieval.selected_source_ids = [rec.source_id, *retrieval.selected_source_ids]
        if rec.section_id not in retrieval.selected_section_ids:
            retrieval.selected_section_ids = ["faq", *retrieval.selected_section_ids]
    return retrieval
