"""Safe whole-turn FAQ: exact/normalized question match, no generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.cm.schemas import FaqRecord, FaqSection
from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_ai.normalize import normalize_search_text

_MULTI_INTENT = re.compile(
    r"\b(book|booking|appoint|appointment|order|human|agent|handoff|photo|video|صورة|حجز|موظف)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FaqExactHit:
    faq_id: str
    language: str
    question: str
    answer: str
    revision: int


def load_faq_section(tenant_id: str) -> FaqSection | None:
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return None
    raw = sections.get("faq")
    if not isinstance(raw, dict):
        return None
    try:
        return FaqSection.model_validate(raw)
    except Exception:
        return None


def faq_fast_path_safe(message: str) -> bool:
    text = message or ""
    if _MULTI_INTENT.search(text):
        return False
    if text.count("?") > 1:
        return False
    lowered = text.lower()
    if " and " in lowered or " و " in f" {text} ":
        return False
    return True


def find_exact_faq(section: FaqSection | None, message: str) -> FaqExactHit | None:
    if not faq_fast_path_safe(message):
        return None
    needle = normalize_search_text(message)
    if not needle or not section:
        return None
    for item in section.items:
        if str(item.status or "draft") != "active":
            continue
        hit = _item_hit(item, needle)
        if hit:
            return hit
    return None


def _item_hit(item: FaqRecord, needle: str) -> FaqExactHit | None:
    if item.status in {"draft", "archived", "restricted", "needs_review"}:
        return None
    for variant in item.variants:
        question = normalize_search_text(variant.question)
        answer = (variant.answer or "").strip()
        if question and question == needle and answer:
            return FaqExactHit(
                faq_id=item.qa_group_id,
                language=variant.language,
                question=variant.question,
                answer=answer,
                revision=int(item.revision or 1),
            )
    return None


def find_published_exact_faq(tenant_id: str, message: str) -> FaqExactHit | None:
    return find_exact_faq(load_faq_section(tenant_id), message)
