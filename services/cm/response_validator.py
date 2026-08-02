"""Deterministic pre-send response validator (plan §12.2 / §12 step 15).

Claim-checks a candidate reply against its AnswerPacket. Purely regex/structural checks —
no additional AI call — so it can run on every response with no added latency/cost risk.
Invalid output must never be sent as if successful (plan §12.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.cm.schemas import AnswerPacket

RESTRICTED_SERVICE_OFFERED = "RESTRICTED_SERVICE_OFFERED"
PRICE_MISMATCH = "PRICE_MISMATCH"
UNSUPPORTED_PRICE_CLAIM = "UNSUPPORTED_PRICE_CLAIM"
WA_NUMBER_MISMATCH = "WA_NUMBER_MISMATCH"
LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"

_PRICE_RE = re.compile(
    r"(?:\$|€|£|usd|eur)\s*(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*(?:\$|€|£|usd|eur|dollars?|دولار)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?<!\w)\+\d{8,15}(?!\w)")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


@dataclass
class ValidationResult:
    ok: bool
    failed_rules: list[str] = field(default_factory=list)
    details: dict[str, str] = field(default_factory=dict)


def _extract_prices(text: str) -> list[float]:
    values: list[float] = []
    for match in _PRICE_RE.finditer(text or ""):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            values.append(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return values


def _extract_phones(text: str) -> list[str]:
    return [re.sub(r"\D", "", p) for p in _PHONE_RE.findall(text or "")]


def _response_language_ok(text: str, response_language: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    has_arabic = bool(_ARABIC_RE.search(stripped))
    if response_language == "ar":
        return has_arabic
    if response_language in ("en", "fr"):
        arabic_chars = len(_ARABIC_RE.findall(stripped))
        return arabic_chars < max(3, int(len(stripped) * 0.2))
    return True


def validate_response(
    response_text: str,
    packet: AnswerPacket,
    *,
    restricted_topic_active_ids: set[str] | None = None,
) -> ValidationResult:
    """Deterministic claim checks. Returns ok + a stable, ordered list of failed rule IDs."""
    failed: list[str] = []
    details: dict[str, str] = {}
    text = response_text or ""

    price_amounts: set[float] = set()
    for fact in packet.facts:
        if fact.kind != "price":
            continue
        for token in re.findall(r"\d+(?:[.,]\d{1,2})?", fact.value):
            try:
                price_amounts.add(float(token.replace(",", ".")))
            except ValueError:
                continue

    mentioned_prices = _extract_prices(text)
    if mentioned_prices:
        if not price_amounts:
            failed.append(UNSUPPORTED_PRICE_CLAIM)
            details[UNSUPPORTED_PRICE_CLAIM] = "Response states a price but the packet has no price facts."
        else:
            mismatched = [p for p in mentioned_prices if not any(abs(p - allowed) < 0.01 for allowed in price_amounts)]
            if mismatched:
                failed.append(PRICE_MISMATCH)
                details[PRICE_MISMATCH] = (
                    f"Response price(s) {mismatched} do not match packet facts {sorted(price_amounts)}."
                )

    phone_facts = {
        re.sub(r"\D", "", fact.value) for fact in packet.facts if fact.kind in ("handoff_phone", "whatsapp_number")
    }
    mentioned_phones = _extract_phones(text)
    if mentioned_phones:
        mismatched_phones = [p for p in mentioned_phones if p not in phone_facts]
        if mismatched_phones:
            failed.append(WA_NUMBER_MISMATCH)
            details[WA_NUMBER_MISMATCH] = f"Response phone(s) {mismatched_phones} not present in packet handoff facts."

    if restricted_topic_active_ids:
        for fact in packet.facts:
            if fact.kind != "service_available" or fact.value != "true":
                continue
            service_id = fact.source_id.split(":", 1)[-1]
            if service_id in restricted_topic_active_ids:
                failed.append(RESTRICTED_SERVICE_OFFERED)
                details[RESTRICTED_SERVICE_OFFERED] = f"Restricted service '{service_id}' marked available in facts."
                break

    if not _response_language_ok(text, packet.response_language):
        failed.append(LANGUAGE_MISMATCH)
        details[LANGUAGE_MISMATCH] = f"Response does not match response_language={packet.response_language!r}."

    return ValidationResult(ok=len(failed) == 0, failed_rules=failed, details=details)
