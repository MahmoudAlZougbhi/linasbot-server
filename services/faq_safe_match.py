"""Safe Smart Answer matching — multi-signal, not blind similarity.

Signals: tenant isolation, language, intent/service/location entities, freshness.
Never returns a cross-tenant FAQ hit. Stale (CM-invalidated) entries are skipped.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_LOCATION_RE = re.compile(
    r"\b(location|address|where|branch|موقع|عنوان|وين|localisation|adresse)\b",
    re.I,
)
_SERVICE_RE = re.compile(
    r"\b(service|treatment|session|جلسة|خدمة|علاج|prestation)\b",
    re.I,
)
_HOURS_RE = re.compile(
    r"\b(hour|open|close|ساعات|دوام|فتح|horaire|ouvert)\b",
    re.I,
)
_ENTITY_TOKEN_RE = re.compile(r"[a-zA-Z\u0600-\u06FF0-9]{2,}")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _ENTITY_TOKEN_RE.findall(text or "")}


def _detect_intent(question: str) -> str:
    q = question or ""
    if _LOCATION_RE.search(q):
        return "location"
    if _HOURS_RE.search(q):
        return "hours"
    if _SERVICE_RE.search(q):
        return "service"
    return "general"


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _is_fresh(entry: dict[str, Any]) -> bool:
    if entry.get("is_active") is False:
        return False
    if str(entry.get("status") or "").lower() in {"archived", "stale", "needs_review"}:
        return False
    if entry.get("stale") is True or entry.get("cm_stale") is True:
        return False
    return True


def _tenant_ok(entry: dict[str, Any], tenant_id: str) -> bool:
    tid = str(entry.get("tenant_id") or "").strip().lower()
    want = (tenant_id or "").strip().lower()
    if not want:
        return False
    # Legacy rows without tenant_id are NOT matched in multi-tenant safe path.
    return tid == want


def _resolve_match_language(*, question: str, language: str, tenant_id: str) -> str:
    """Prefer broad inbound detection so saved per-language Q&A works beyond ar/en/fr/franco."""
    from services.cm.customer_language_detect import detect_broad_customer_language, normalize_language_code
    from services.language_detection_service import language_detection_service

    normalized_hint = language_detection_service.normalize_training_language(language, default="")
    detected = detect_broad_customer_language(
        message=question or "",
        conversation_id=f"faq-match:{tenant_id}",
    )
    detected = normalize_language_code(detected) or normalized_hint or "ar"
    if detected == "franco":
        return "ar"
    if normalized_hint and detected in {"", "en", "ar", "fr"} and normalized_hint not in {"", "en", "ar", "fr"}:
        return normalized_hint
    return detected or normalized_hint or "ar"


def score_candidate(
    *,
    question: str,
    language: str,
    entry: dict[str, Any],
    intent: str,
    service_hint: str | None = None,
    location_hint: str | None = None,
) -> dict[str, Any]:
    q_tokens = _tokens(question)
    e_q = str(entry.get("question") or "")
    e_a = str(entry.get("answer") or "")
    e_tokens = _tokens(e_q) | _tokens(e_a)
    sim = _similarity(question, e_q)
    entry_lang = str(entry.get("language") or "").strip().lower()
    lang_ok = (not language) or entry_lang == language or entry_lang in {"", "unknown"}
    entry_intent = str(entry.get("intent") or _detect_intent(e_q))
    intent_ok = intent == "general" or entry_intent in {intent, "general"}
    overlap = len(q_tokens & e_tokens) / max(1, len(q_tokens))
    service_ok = True
    if service_hint:
        service_ok = _norm(service_hint) in _norm(e_q + " " + e_a)
    location_ok = True
    if location_hint:
        location_ok = _norm(location_hint) in _norm(e_q + " " + e_a)
    # Weighted score — similarity alone is never enough.
    score = (
        0.45 * sim
        + 0.20 * (1.0 if lang_ok else 0.0)
        + 0.15 * (1.0 if intent_ok else 0.0)
        + 0.10 * min(1.0, overlap)
        + 0.05 * (1.0 if service_ok else 0.0)
        + 0.05 * (1.0 if location_ok else 0.0)
    )
    accept = _is_fresh(entry) and lang_ok and intent_ok and service_ok and location_ok and sim >= 0.82 and score >= 0.78
    return {
        "score": round(score, 4),
        "similarity": round(sim, 4),
        "accept": accept,
        "lang_ok": lang_ok,
        "intent_ok": intent_ok,
        "service_ok": service_ok,
        "location_ok": location_ok,
        "entry_intent": entry_intent,
    }


def find_safe_faq_match(
    *,
    tenant_id: str,
    question: str,
    language: str = "ar",
    service_hint: str | None = None,
    location_hint: str | None = None,
    qa_pairs: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return a safe match dict or None. Never invents answers."""
    from services.faq_entitlements import get_faq_entitlement

    ent = get_faq_entitlement(tenant_id)
    if not ent.get("faq_enabled"):
        return None

    if qa_pairs is None:
        from services.local_qa_service import local_qa_service

        qa_pairs = list(local_qa_service.qa_pairs)

    lang = _resolve_match_language(question=question, language=language, tenant_id=tenant_id)
    intent = _detect_intent(question)
    best: dict[str, Any] | None = None
    best_score = 0.0

    for entry in qa_pairs:
        if not _tenant_ok(entry, tenant_id):
            continue
        if not _is_fresh(entry):
            continue
        scored = score_candidate(
            question=question,
            language=lang,
            entry=entry,
            intent=intent,
            service_hint=service_hint,
            location_hint=location_hint,
        )
        if not scored["accept"]:
            continue
        if scored["score"] > best_score:
            best_score = scored["score"]
            best = {
                "qa_pair": entry,
                "match_score": scored["similarity"],
                "safe_score": scored["score"],
                "tier": "safe_semantic",
                "matched_language": str(entry.get("language") or lang),
                "intent": intent,
                "signals": {
                    "lang_ok": scored["lang_ok"],
                    "intent_ok": scored["intent_ok"],
                    "service_ok": scored["service_ok"],
                    "location_ok": scored["location_ok"],
                },
            }
    return best
