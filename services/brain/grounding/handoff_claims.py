"""Ground transfer-success claims against escalate_to_human receipts. Not intent detection."""

from __future__ import annotations

from services.brain.grounding import extract

HANDOFF_SUCCESS_MARKERS: tuple[str, ...] = (
    "transferred you",
    "transfer you",
    "connect you",
    "connected you",
    "handing you over",
    "hand you over",
    "handover to",
    "حوّلتك",
    "حولتك",
    "رح حوّلك",
    "رح حولك",
    "تم التحويل",
    "أوصلتك",
    "اوصلتك",
)


def _escalate_success(receipts: list[str]) -> bool:
    for line in receipts:
        low = extract.marker_text(line)
        if "escalate_to_human" not in low:
            continue
        if "success" in low and "failure" not in low:
            return True
    return False


def ungrounded_handoff_claims(reply_text: str, receipts: list[str] | None = None) -> list[str]:
    normalized = extract.marker_text(reply_text)
    markers = tuple(extract.marker_text(item) or item for item in HANDOFF_SUCCESS_MARKERS)
    claim = extract.has_marker(normalized, markers)
    if not claim:
        return []
    if _escalate_success([str(item) for item in (receipts or []) if str(item).strip()]):
        return []
    return [f"handoff:{claim}"]
