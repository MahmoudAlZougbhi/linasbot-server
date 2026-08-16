"""Published FAQ fast path — strict V10 direct reply, legacy path behind rollback flag."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.cm.version_store import load_published_content
from services.customer_reply_v2.faq_eligibility import (
    SEMANTIC_FAQ_MIN_SCORE,
    FaqTurnGuards,
    canonical_faq_language,
    channel_incompatible,
    faq_published_has_resources,
    is_context_dependent_question,
    languages_compatible,
    mixed_or_uncovered_reason,
    pre_match_block_reason,
)
from services.customer_reply_v2.faq_evidence import faq_candidate_payload
from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled
from services.faq_answer_localize import localize_faq_answer

__all__ = [
    "FaqFastPathResult",
    "FaqTurnGuards",
    "SEMANTIC_FAQ_MIN_SCORE",
    "is_context_dependent_question",
    "try_faq_fast_path",
]


@dataclass
class FaqFastPathResult:
    hit: bool
    answer: str = ""
    reason: str = ""
    metadata: dict[str, Any] | None = None
    evidence_candidates: list[dict[str, Any]] = field(default_factory=list)
    checked: bool = True


def _qa_ids(qa: dict[str, Any], *, source_id: str | None = None) -> tuple[str, str]:
    faq_id = str(qa.get("qa_group_id") or qa.get("id") or source_id or "").strip()
    revision = str(qa.get("revision") or qa.get("published_revision") or "").strip()
    return faq_id, revision


def _lookup_published_variant(
    *,
    tenant_id: str,
    qa_group_id: str,
    language: str,
) -> dict[str, Any] | None:
    if not qa_group_id:
        return None
    try:
        pointer, sections = load_published_content(tenant_id)
    except Exception:
        return None
    payload = sections.get("faq") or {}
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return None
    want = canonical_faq_language(language)
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("qa_group_id") or "").strip() != qa_group_id:
            continue
        status = str(item.get("status") or "active").strip().lower()
        if status not in {"", "active"}:
            return None
        revision = str(item.get("revision") or pointer.content_version_id or "")
        for variant in item.get("variants") or []:
            if not isinstance(variant, dict):
                continue
            if canonical_faq_language(variant.get("language")) != want:
                continue
            question = str(variant.get("question") or "").strip()
            answer = str(variant.get("answer") or "").strip()
            if question and answer:
                return {"question": question, "answer": answer, "revision": revision, "status": status}
    return None


def _meta(
    *,
    faq_id: str,
    faq_revision: str,
    match_type: str,
    match_score: Any,
    channel: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = {
        "faq_id": faq_id,
        "faq_revision": faq_revision,
        "match_type": match_type,
        "match_score": match_score,
        "channel": channel,
        "faq_direct_reply": True,
    }
    if extra:
        out.update(extra)
    return out


def _ineligible(
    *,
    reason: str,
    answer: str = "",
    question: str = "",
    metadata: dict[str, Any] | None = None,
) -> FaqFastPathResult:
    meta = dict(metadata or {})
    meta["faq_direct_reply"] = False
    meta["ineligible_reason"] = reason
    candidates = []
    if answer or meta.get("faq_id"):
        candidates.append(faq_candidate_payload(meta, answer=answer, question=question))
    return FaqFastPathResult(
        hit=False,
        reason=reason,
        metadata=meta or None,
        evidence_candidates=candidates,
    )


async def _legacy_localized_answer(
    *,
    answer: str,
    matched_language: str | None,
    response_language: str,
    metadata: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    localized = await localize_faq_answer(
        answer=answer,
        source_language=matched_language,
        target_language=response_language,
    )
    meta = dict(metadata or {})
    if matched_language and matched_language != response_language:
        meta["matched_language"] = matched_language
        meta["response_language"] = response_language
        meta["localized"] = localized != answer
    return localized, meta or None


async def _semantic_hits(*, tenant_id: str, index_id: str, message: str, language: str | None) -> list[dict[str, Any]]:
    from services.cm.semantic_index import search as semantic_search

    try:
        return await semantic_search(
            tenant_id=tenant_id,
            index_id=index_id,
            query=message,
            kind="faq",
            language=language,
            top_k=2,
        )
    except Exception:
        return []


async def _finish_match(
    *,
    tenant_id: str,
    message: str,
    answer: str,
    question: str,
    matched_language: str,
    response_language: str,
    match_type: str,
    match_score: Any,
    faq_id: str,
    faq_revision: str,
    tags: list[str] | None,
    channel: str,
    strict: bool,
    extra: dict[str, Any] | None = None,
) -> FaqFastPathResult:
    meta_extra = dict(extra or {})
    meta_extra["question"] = question
    meta_extra["answer"] = answer
    meta_extra["matched_language"] = matched_language
    meta_extra["response_language"] = response_language
    if not strict:
        localized, meta = await _legacy_localized_answer(
            answer=answer,
            matched_language=matched_language,
            response_language=response_language,
            metadata=_meta(
                faq_id=faq_id,
                faq_revision=faq_revision,
                match_type=match_type,
                match_score=match_score,
                channel=channel,
                extra=meta_extra,
            ),
        )
        return FaqFastPathResult(hit=True, answer=localized, reason=match_type, metadata=meta)

    if not str(question or "").strip():
        if match_type in {"faq_exact", "faq_direct", "exact"}:
            question = message
            meta_extra["question"] = question
        else:
            return _ineligible(
                reason="partial_coverage",
                answer=answer,
                question=question,
                metadata=_meta(
                    faq_id=faq_id,
                    faq_revision=faq_revision,
                    match_type=match_type,
                    match_score=match_score,
                    channel=channel,
                    extra=meta_extra,
                ),
            )

    uncovered = mixed_or_uncovered_reason(message=message, faq_question=question)
    if uncovered:
        return _ineligible(
            reason=uncovered,
            answer=answer,
            question=question,
            metadata=_meta(
                faq_id=faq_id,
                faq_revision=faq_revision,
                match_type=match_type,
                match_score=match_score,
                channel=channel,
                extra=meta_extra,
            ),
        )
    if faq_published_has_resources(tenant_id=tenant_id, faq_id=faq_id):
        return _ineligible(
            reason="faq_needs_resource",
            answer=answer,
            question=question,
            metadata=_meta(
                faq_id=faq_id,
                faq_revision=faq_revision,
                match_type=match_type,
                match_score=match_score,
                channel=channel,
                extra=meta_extra,
            ),
        )

    stored_answer = answer
    stored_question = question
    stored_lang = matched_language
    stored_revision = faq_revision
    if not languages_compatible(matched_language, response_language):
        variant = _lookup_published_variant(
            tenant_id=tenant_id,
            qa_group_id=faq_id,
            language=response_language,
        )
        if not variant:
            return _ineligible(
                reason="language_mismatch",
                answer=answer,
                question=question,
                metadata=_meta(
                    faq_id=faq_id,
                    faq_revision=faq_revision,
                    match_type=match_type,
                    match_score=match_score,
                    channel=channel,
                    extra=meta_extra,
                ),
            )
        stored_answer = str(variant["answer"])
        stored_question = str(variant["question"])
        stored_lang = response_language
        stored_revision = str(variant.get("revision") or faq_revision)
        meta_extra["variant_language"] = stored_lang

    bad_channel = channel_incompatible(channel=channel, answer=stored_answer, tags=tags)
    if bad_channel:
        return _ineligible(
            reason=bad_channel,
            answer=stored_answer,
            question=stored_question,
            metadata=_meta(
                faq_id=faq_id,
                faq_revision=stored_revision,
                match_type=match_type,
                match_score=match_score,
                channel=channel,
                extra=meta_extra,
            ),
        )

    meta = _meta(
        faq_id=faq_id,
        faq_revision=stored_revision,
        match_type=match_type,
        match_score=match_score,
        channel=channel,
        extra={**meta_extra, "matched_language": stored_lang, "localized": False},
    )
    reason = "faq_exact" if match_type in {"faq_exact", "exact"} else match_type
    return FaqFastPathResult(hit=True, answer=stored_answer, reason=reason, metadata=meta)


async def try_faq_fast_path(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    response_language: str | None = None,
    has_unresolved_context_refs: bool = False,
    guards: FaqTurnGuards | None = None,
    channel: str = "",
    strict: bool | None = None,
) -> FaqFastPathResult:
    """Exact / normalized then conservative semantic FAQ. Published only. Tenant-scoped."""
    use_strict = customer_ai_v10_runtime_enabled() if strict is None else strict
    visitor_language = (response_language or detected_language or "en").strip().lower()
    turn = guards or FaqTurnGuards(
        has_unresolved_context_refs=has_unresolved_context_refs,
        channel=channel,
        response_language=visitor_language,
        detected_language=detected_language,
    )
    if use_strict:
        blocked = pre_match_block_reason(message, turn)
        if blocked:
            return FaqFastPathResult(hit=False, reason=blocked, metadata={"faq_direct_reply": False})
    elif is_context_dependent_question(message) or has_unresolved_context_refs:
        return FaqFastPathResult(hit=False, reason="context_dependent")

    pointer, _sections = load_published_content(tenant_id)
    published_revision = str(pointer.content_version_id or "")

    from services.local_qa_service import local_qa_service

    tiered = await local_qa_service.find_match_with_tier(message, detected_language)
    if tiered:
        qa = tiered.get("qa_pair") or {}
        answer = str(qa.get("answer") or "").strip()
        question = str(qa.get("question") or "").strip()
        if answer:
            faq_id, faq_revision = _qa_ids(qa)
            faq_revision = faq_revision or published_revision
            matched_language = str(tiered.get("matched_language") or qa.get("language") or detected_language)
            match_type = "faq_exact" if tiered.get("tier") == "exact" else "faq_direct"
            return await _finish_match(
                tenant_id=tenant_id,
                message=message,
                answer=answer,
                question=question,
                matched_language=matched_language,
                response_language=visitor_language,
                match_type=match_type,
                match_score=tiered.get("match_score"),
                faq_id=faq_id,
                faq_revision=faq_revision,
                tags=list(qa.get("tags") or []),
                channel=channel or turn.channel,
                strict=use_strict,
                extra={"tier": tiered.get("tier")},
            )

    from services.cm.version_store import read_published_pointer

    pub = read_published_pointer(tenant_id)
    index_id = pub.index_version_id if pub else None
    if not index_id:
        return FaqFastPathResult(hit=False, reason="index_unavailable")

    hits = await _semantic_hits(tenant_id=tenant_id, index_id=index_id, message=message, language=detected_language)
    if not hits:
        hits = await _semantic_hits(tenant_id=tenant_id, index_id=index_id, message=message, language=None)
    if not hits:
        return FaqFastPathResult(hit=False, reason="faq_miss")

    strong = [h for h in hits if float(h.get("score") or 0) >= SEMANTIC_FAQ_MIN_SCORE]
    if len(strong) >= 2:
        scores = [float(h.get("score") or 0) for h in strong[:2]]
        if abs(scores[0] - scores[1]) < 0.02:
            return FaqFastPathResult(hit=False, reason="faq_ambiguous")

    if strong:
        top = strong[0]
        metadata = top.get("metadata") or {}
        answer = str(metadata.get("answer") or "").strip()
        question = str(metadata.get("question") or metadata.get("title") or "").strip()
        if answer:
            faq_id = str(top.get("source_id") or metadata.get("qa_group_id") or metadata.get("id") or "").strip()
            matched_language = str(metadata.get("language") or detected_language)
            return await _finish_match(
                tenant_id=tenant_id,
                message=message,
                answer=answer,
                question=question,
                matched_language=matched_language,
                response_language=visitor_language,
                match_type="faq_semantic",
                match_score=top.get("score"),
                faq_id=faq_id,
                faq_revision=str(metadata.get("revision") or published_revision),
                tags=list(metadata.get("tags") or []),
                channel=channel or turn.channel,
                strict=use_strict,
                extra={"source_id": top.get("source_id")},
            )
    return FaqFastPathResult(hit=False, reason="faq_miss")
