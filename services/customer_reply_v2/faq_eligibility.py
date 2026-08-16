"""Conservative FAQ-direct eligibility guards (not product/appointment routing)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.cm.iso639_languages import normalize_language_code

SEMANTIC_FAQ_MIN_SCORE = 0.90
COMMENT_STATIC_ANSWER_MAX_CHARS = 900

_CONTEXT_DEPENDENT = re.compile(
    r"(قديش\s+هيدا|قديش\s+هيدي|this\s+one|that\s+one|the\s+second|"
    r"yes,?\s+that\s+branch|نفس\s+الشي|نفسها|هيدا\s*\?|هيدي\s*\?|"
    r"how\s+much\s+is\s+(this|that)|c'?est\s+combien)",
    re.I,
)

_GREETING_PREFIX = re.compile(
    r"^\s*(hi|hello|hey|yo|hola|bonjour|salut|مرحبا|اهلا|أهلاً?|السلام\s+عليكم|"
    r"سلام|slm|hiya|good\s+(morning|evening|afternoon))\b[\s,!.،؟]*",
    re.I,
)

_EXTRA_INTENT = re.compile(
    r"(موعد|ميعاد|احجز|حجز|طلب\b|اوردر|"
    r"\bappointment\b|\bbook\b|\border\b|"
    r"ابعت(?:ي|لي)?|ابعث|صوره|صورة|صور|فيديو|"
    r"send\s+me\s+(a\s+)?(pic|photo|image|video)|"
    r"\bpause\b|\bresume\b|\bcancel\b|"
    r"طولي|وزني|عمري|ضيف|بدل|شيل)",
    re.I,
)

_CONJUNCTION_EXTRA = re.compile(
    r"(وبدي|وكمان|وبعدين|وابعت|و\s*كمان|"
    r"\band\s+(i\s+want|also|book|send)|"
    r"\bplus\b|\bas\s+well\b)",
    re.I,
)

_CHANNEL_TAGS = {
    "instagram_dm",
    "facebook_dm",
    "instagram_comment",
    "facebook_comment",
    "whatsapp_dm",
}


@dataclass(frozen=True)
class FaqTurnGuards:
    has_attachment: bool = False
    has_reply_to: bool = False
    has_open_draft: bool = False
    has_ai_guidance_comment_rule: bool = False
    has_unresolved_context_refs: bool = False
    channel: str = ""
    response_language: str = ""
    detected_language: str = ""


def is_context_dependent_question(message: str) -> bool:
    return bool(_CONTEXT_DEPENDENT.search(message or ""))


def normalize_faq_text(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    value = re.sub(r"[؟?!.،,;:]", "", value)
    value = value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    value = value.replace("ة", "ه").replace("ى", "ي")
    return value.lower()


def _lang_key(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"franco", "arabizi", "ar-franco"}:
        return "franco"
    return normalize_language_code(raw) or raw


def canonical_faq_language(value: str | None) -> str:
    return _lang_key(value)


def languages_compatible(source: str | None, target: str | None) -> bool:
    src = _lang_key(source)
    dst = _lang_key(target)
    if not dst or not src or src == dst:
        return True
    return {src, dst} <= {"ar", "franco"}


def pre_match_block_reason(message: str, guards: FaqTurnGuards) -> str | None:
    if guards.has_attachment:
        return "attachment"
    if guards.has_reply_to:
        return "reply_to"
    if guards.has_open_draft:
        return "open_draft"
    if guards.has_ai_guidance_comment_rule:
        return "ai_guidance_comment_rule"
    if guards.has_unresolved_context_refs or is_context_dependent_question(message):
        return "context_dependent"
    return None


def greeting_plus_question(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    stripped = _GREETING_PREFIX.sub("", text, count=1).strip()
    return bool(stripped) and stripped != text.strip()


def faq_covers_full_message(*, message: str, faq_question: str) -> bool:
    msg = normalize_faq_text(message)
    question = normalize_faq_text(faq_question)
    if not msg or not question:
        return False
    if msg == question:
        return True
    greeting_stripped = normalize_faq_text(_GREETING_PREFIX.sub("", message or "", count=1))
    if greeting_stripped and greeting_stripped == question:
        return False
    if question in msg:
        remainder = msg.replace(question, " ", 1)
        remainder = re.sub(r"\s+", " ", remainder).strip()
        if not remainder:
            return True
        if _EXTRA_INTENT.search(remainder) or _CONJUNCTION_EXTRA.search(remainder):
            return False
        if len(remainder.split()) >= 2:
            return False
    return False


def mixed_or_uncovered_reason(*, message: str, faq_question: str) -> str | None:
    if greeting_plus_question(message):
        return "greeting_plus_question"
    if not faq_covers_full_message(message=message, faq_question=faq_question):
        if _EXTRA_INTENT.search(message or "") or _CONJUNCTION_EXTRA.search(message or ""):
            return "mixed_intent"
        return "partial_coverage"
    if _EXTRA_INTENT.search(message or "") and not _EXTRA_INTENT.search(faq_question or ""):
        return "mixed_intent"
    return None


def faq_published_has_resources(*, tenant_id: str, faq_id: str) -> bool:
    """True when the published FAQ item has customer-visible Image/Video/File/Link resources."""
    from services.cm.resource_attachment import resource_summary
    from services.cm.version_store import load_published_content

    want = str(faq_id or "").strip()
    if not want or not str(tenant_id or "").strip():
        return False
    try:
        _pointer, sections = load_published_content(tenant_id)
    except Exception:
        return False
    payload = sections.get("faq") or {}
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        gid = str(item.get("qa_group_id") or item.get("id") or "").strip()
        if gid != want:
            continue
        return bool(resource_summary(item.get("attachments")).get("has_resources"))
    return False


def channel_incompatible(*, channel: str, answer: str, tags: list[str] | None) -> str | None:
    channel_tags = {str(t).strip().lower() for t in (tags or [])} & _CHANNEL_TAGS
    ch = (channel or "").strip().lower()
    if channel_tags and ch and ch not in channel_tags:
        return "channel_incompatible"
    if "comment" in ch and len(answer or "") > COMMENT_STATIC_ANSWER_MAX_CHARS:
        return "channel_incompatible"
    return None
