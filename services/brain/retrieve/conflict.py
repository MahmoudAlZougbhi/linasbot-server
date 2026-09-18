"""Source authority conflict resolution for Customer Brain evidence."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.entity_identity import canonical_id, is_bundle_name
from services.brain.grounding import extract
from services.brain.retrieve.authority import AUTHORITY, authority_for_family

SOURCE_PRIORITY = [
    "tool_receipt",
    "structured_published",
    "exact_faq",
    "published_cm",
    "uploaded_knowledge",
    "durable_memory",
    "conversation_text",
]


def _entity_key(item: EvidenceItem) -> str:
    extra = item.extra if isinstance(item.extra, dict) else {}
    cid = canonical_id(extra.get("entity_id"), extra.get("catalog_item_id"))
    if cid:
        return cid
    from services.brain.normalize import normalize_search_text

    title = normalize_search_text(item.title or "")
    if title:
        return f"title:{title}"
    return canonical_id(item.source_id, item.evidence_id)


def _amounts(item: EvidenceItem) -> set[str]:
    extra = item.extra if isinstance(item.extra, dict) else {}
    found = {part.split("|", 1)[0] for part in extract.amounts(f"{item.title}\n{item.text}")}
    if extra.get("amount") is not None:
        found.add(str(extra.get("amount")))
    return found


def detect_entity_amount_conflicts(items: list[EvidenceItem]) -> list[dict[str, Any]]:
    by_entity: dict[str, set[str]] = {}
    for item in items:
        amounts = _amounts(item)
        if not amounts:
            continue
        key = _entity_key(item)
        by_entity.setdefault(key, set()).update(amounts)
    return [
        {"type": "amount", "entity_id": entity_id, "values": sorted(values), "reason": "conflicting_amounts_same_entity"}
        for entity_id, values in by_entity.items()
        if len(values) > 1
    ]


def resolve_conflicts(bundle: EvidenceBundle, *, query: str = "") -> dict[str, Any]:
    conflicts = detect_entity_amount_conflicts(list(bundle.items))
    by_auth = sorted(
        bundle.items,
        key=lambda item: (authority_for_family(item.source_family), item.revision or "", item.evidence_id),
        reverse=True,
    )
    winners: list[EvidenceItem] = []
    dropped: list[EvidenceItem] = []
    decisions: list[dict[str, Any]] = []
    seen_by_entity: dict[str, set[str]] = {}
    for item in by_auth:
        key = _entity_key(item)
        amounts = _amounts(item)
        prior = seen_by_entity.get(key) or set()
        if amounts and prior and amounts.isdisjoint(prior):
            dropped.append(item)
            decisions.append(
                {
                    "loser_id": item.evidence_id,
                    "loser_family": item.source_family,
                    "entity_id": key,
                    "winner_id": next((w.evidence_id for w in winners if _entity_key(w) == key), ""),
                    "reason": "lower_authority_amount_conflict",
                    "authority": authority_for_family(item.source_family),
                }
            )
            continue
        winners.append(item)
        seen_by_entity.setdefault(key, set()).update(amounts)
    if query:
        standalone = [item for item in winners if not is_bundle_name(item.title)]
        bundles = [item for item in winners if is_bundle_name(item.title)]
        from services.brain.entity_identity import score_label

        if standalone and bundles:
            best_stand = max(score_label(query, item.title) for item in standalone)
            best_bundle = max(score_label(query, item.title) for item in bundles)
            if best_stand >= 40 and best_stand > best_bundle + 4:
                kept_ids = {item.evidence_id for item in standalone} | {
                    item.evidence_id for item in winners if item.source_family not in {"services", "prices", "products"}
                }
                filtered = [item for item in winners if item.evidence_id in kept_ids or not is_bundle_name(item.title)]
                if filtered:
                    winners = filtered
    return {
        "resolved": winners,
        "dropped": dropped,
        "decisions": decisions,
        "conflicts": conflicts,
        "source_priority": list(SOURCE_PRIORITY),
        "authority_table": dict(AUTHORITY),
    }


def apply_authority(bundle: EvidenceBundle, *, query: str = "") -> tuple[EvidenceBundle, dict[str, Any]]:
    result = resolve_conflicts(bundle, query=query)
    resolved = list(result["resolved"])
    return (
        bundle.model_copy(update={"items": resolved, "conflicts": [str(c) for c in result.get("conflicts") or []]}),
        result,
    )
