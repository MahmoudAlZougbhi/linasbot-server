"""Deterministic claim checks against selected evidence. Not an LLM critic.

Every check is fail-closed: a claim is ungrounded unless the same surface (money, clock
time, phone, url, stock wording, booking receipt) exists in the evidence bundle or in the
action receipts for this turn.
"""

from __future__ import annotations

from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.grounding import extract


def _evidence_text(bundle: EvidenceBundle) -> str:
    return "\n".join(f"{item.title}\n{item.text}" for item in bundle.items)


def ungrounded_amounts(reply_text: str, bundle: EvidenceBundle) -> list[str]:
    allowed = extract.amounts(_evidence_text(bundle))
    return sorted(extract.amounts(reply_text) - allowed)


def _amount_reasons(reply_text: str, corpus: str) -> list[str]:
    allowed = extract.amounts(corpus)
    return [f"amount:{claim}" for claim in sorted(extract.amounts(reply_text) - allowed)]


def _hours_reasons(reply_text: str, corpus: str) -> list[str]:
    reasons: list[str] = []
    allowed = extract.clock_surfaces(corpus)
    claims = extract.clock_claims(reply_text)
    for variants in claims:
        if not (variants & allowed):
            reasons.append(f"hours:{min(variants)}")
    open_claim = extract.has_marker(extract.marker_text(reply_text), extract.OPEN_MARKERS)
    if open_claim and not allowed:
        reasons.append("hours:no_hours_evidence")
    if claims or open_claim:
        for day in sorted(extract.days(reply_text) - extract.days(corpus)):
            reasons.append(f"hours:day:{day}")
    return reasons


def _phone_reasons(reply_text: str, corpus: str) -> list[str]:
    allowed = extract.phones(corpus)
    return [
        f"phone:{claim}"
        for claim in sorted(extract.phones(reply_text))
        if not extract.phone_grounded(claim, allowed)
    ]


def _url_reasons(reply_text: str, corpus: str) -> list[str]:
    allowed = extract.urls(corpus)
    body = extract.flat(corpus)
    return [f"url:{claim}" for claim in sorted(extract.urls(reply_text)) if claim not in allowed and claim not in body]


def _stock_reasons(reply_text: str, corpus: str) -> list[str]:
    claim = extract.has_marker(extract.marker_text(reply_text), extract.STOCK_CLAIMS)
    if not claim:
        return []
    corpus_markers = extract.marker_text(corpus)
    negative = ("out of stock", "sold out", "unavailable", "غير متوفر")
    positive = ("in stock", "back in stock", "available now", "we have it available", "متوفر", "موجود بالمخزن")
    claim_l = claim.casefold()
    if claim_l in {item.casefold() for item in negative} or "out of stock" in claim_l or "sold out" in claim_l:
        if extract.has_marker(corpus_markers, negative):
            return []
        return [f"stock:{claim}"]
    if claim_l in {item.casefold() for item in positive} or claim_l == "متوفر":
        if extract.has_marker(corpus_markers, positive):
            return []
        # Broad availability wording in evidence still grounds a positive claim.
        if extract.has_marker(corpus_markers, ("available", "availability", "inventory", "stock", "متوفر", "الكميه", "المخزن")):
            return []
        return [f"stock:{claim}"]
    if extract.has_marker(corpus_markers, extract.STOCK_SUPPORT):
        return []
    return [f"stock:{claim}"]


def _booking_reasons(reply_text: str, receipts: list[str]) -> list[str]:
    claim = extract.matched_pattern(extract.marker_text(reply_text), extract.BOOKING_CLAIM_PATTERNS)
    if not claim:
        return []
    for receipt in receipts:
        if extract.has_marker(extract.marker_text(receipt), extract.RECEIPT_SUCCESS):
            return []
    return [f"booking:{claim}"]


def ungrounded_claims(
    reply_text: str,
    bundle: EvidenceBundle,
    receipts: list[str] | None = None,
) -> list[str]:
    """Reasons the reply is not supported by evidence. Empty list means grounded."""
    text = (reply_text or "").strip()
    if not text:
        return ["reply:empty"]
    if not bundle.items and not receipts:
        return ["evidence:empty"]
    receipt_lines = [line for line in (receipts or []) if str(line).strip()]
    corpus = "\n".join([_evidence_text(bundle), *receipt_lines])
    reasons = [
        *_amount_reasons(text, corpus),
        *_hours_reasons(text, corpus),
        *_phone_reasons(text, corpus),
        *_url_reasons(text, corpus),
        *_stock_reasons(text, corpus),
        *_booking_reasons(text, receipt_lines),
    ]
    return list(dict.fromkeys(reasons))


def evidence_supports_text(
    reply_text: str,
    bundle: EvidenceBundle,
    receipts: list[str] | None = None,
) -> bool:
    if not bundle.items:
        return False
    return not ungrounded_claims(reply_text, bundle, receipts)
