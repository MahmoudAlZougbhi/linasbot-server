"""Claim-level grounding statuses for Customer Brain answers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.grounding import extract
from services.customer_ai.grounding.facts import ungrounded_claims

ClaimStatus = Literal[
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNSUPPORTED",
    "NON_FACTUAL",
]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SOFT_FACT = re.compile(r"\b(offer|provide|available|open|branch|price|cost|book)\b", re.I)


@dataclass(frozen=True)
class ClaimVerdict:
    claim: str
    status: ClaimStatus
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""


def _split_claims(reply_text: str) -> list[str]:
    text = (reply_text or "").strip()
    if not text:
        return []
    return [chunk.strip() for chunk in _SENT_SPLIT.split(text) if chunk.strip()]


def _is_factual(sentence: str) -> bool:
    markers = extract.marker_text(sentence)
    if extract.amounts(sentence):
        return True
    if extract.phones(sentence):
        return True
    if extract.urls(sentence):
        return True
    if extract.clock_surfaces(sentence):
        return True
    if extract.has_marker(markers, extract.STOCK_CLAIMS):
        return True
    if extract.matched_pattern(markers, extract.BOOKING_CLAIM_PATTERNS):
        return True
    return bool(_SOFT_FACT.search(sentence))


def verify_claims(
    reply_text: str,
    bundle: EvidenceBundle,
    *,
    receipts: list[str] | None = None,
) -> list[ClaimVerdict]:
    """Deterministic claim verifier. Fail closed on unsupported factual claims."""
    corpus = "\n".join(item.text for item in bundle.items)
    corpus_ids = tuple(item.evidence_id for item in bundle.items)
    verdicts: list[ClaimVerdict] = []
    for sentence in _split_claims(reply_text):
        if not _is_factual(sentence):
            verdicts.append(ClaimVerdict(sentence, "NON_FACTUAL"))
            continue
        if not bundle.items:
            verdicts.append(ClaimVerdict(sentence, "UNSUPPORTED", reason="empty_evidence"))
            continue
        local_bad = ungrounded_claims(sentence, bundle, receipts)
        if local_bad:
            verdicts.append(
                ClaimVerdict(
                    sentence,
                    "UNSUPPORTED",
                    evidence_ids=corpus_ids,
                    reason=",".join(local_bad),
                )
            )
            continue
        sent_tokens = set(extract.marker_text(sentence).split())
        corp_tokens = set(extract.marker_text(corpus).split())
        if not sent_tokens:
            verdicts.append(ClaimVerdict(sentence, "NON_FACTUAL"))
            continue
        overlap = len(sent_tokens & corp_tokens) / max(1, len(sent_tokens))
        if overlap >= 0.55:
            verdicts.append(ClaimVerdict(sentence, "SUPPORTED", evidence_ids=corpus_ids))
        elif overlap >= 0.3:
            verdicts.append(ClaimVerdict(sentence, "PARTIALLY_SUPPORTED", evidence_ids=corpus_ids))
        else:
            verdicts.append(
                ClaimVerdict(sentence, "UNSUPPORTED", evidence_ids=corpus_ids, reason="weak_overlap")
            )
    return verdicts


def claims_fail_closed(verdicts: list[ClaimVerdict]) -> bool:
    return any(v.status in {"UNSUPPORTED", "CONTRADICTED"} for v in verdicts)
