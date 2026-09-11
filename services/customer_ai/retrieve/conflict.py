"""Source authority conflict resolution for Customer Brain evidence."""

from __future__ import annotations

import re
from typing import Any

from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.grounding.contradiction import detect_amount_contradictions
from services.customer_ai.retrieve.authority import AUTHORITY, authority_for_family

SOURCE_PRIORITY = [
    "tool_receipt",
    "structured_published",
    "exact_faq",
    "published_cm",
    "uploaded_knowledge",
    "durable_memory",
    "conversation_text",
]

_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(USD|LBP|EUR|GBP|\$|€)?", re.I)


def resolve_conflicts(bundle: EvidenceBundle) -> dict[str, Any]:
    text = "\n".join(item.text for item in bundle.items)
    conflicts = detect_amount_contradictions(text)
    if not conflicts:
        return {
            "resolved": list(bundle.items),
            "dropped": [],
            "decisions": [],
            "conflicts": [],
            "source_priority": list(SOURCE_PRIORITY),
            "authority_table": dict(AUTHORITY),
        }

    by_auth = sorted(
        bundle.items,
        key=lambda item: (authority_for_family(item.source_family), item.revision or "", item.evidence_id),
        reverse=True,
    )
    winners: list[EvidenceItem] = []
    dropped: list[EvidenceItem] = []
    decisions: list[dict[str, Any]] = []
    seen_amounts: set[str] = set()
    for item in by_auth:
        amounts = {f"{m.group(1)}".lower() for m in _AMOUNT.finditer(item.text or "")}
        if amounts and seen_amounts and amounts.isdisjoint(seen_amounts):
            dropped.append(item)
            decisions.append(
                {
                    "loser_id": item.evidence_id,
                    "loser_family": item.source_family,
                    "winner_id": winners[0].evidence_id if winners else "",
                    "reason": "lower_authority_amount_conflict",
                    "authority": authority_for_family(item.source_family),
                }
            )
            continue
        winners.append(item)
        seen_amounts |= amounts
    return {
        "resolved": winners,
        "dropped": dropped,
        "decisions": decisions,
        "conflicts": conflicts,
        "source_priority": list(SOURCE_PRIORITY),
        "authority_table": dict(AUTHORITY),
    }


def apply_authority(bundle: EvidenceBundle) -> tuple[EvidenceBundle, dict[str, Any]]:
    result = resolve_conflicts(bundle)
    resolved = list(result["resolved"])
    return (
        bundle.model_copy(update={"items": resolved, "conflicts": [str(c) for c in result.get("conflicts") or []]}),
        result,
    )
