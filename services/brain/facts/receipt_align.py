"""Align tool receipts with evidence identity so rejected facts are not re-injected."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.evidence import EvidenceBundle
from services.brain.entity_identity import canonical_id


def dropped_entity_ids(conflict_meta: dict[str, Any] | None) -> set[str]:
    out: set[str] = set()
    for row in (conflict_meta or {}).get("decisions") or []:
        if str(row.get("reason") or "") != "lower_authority_amount_conflict":
            continue
        entity_id = canonical_id(row.get("entity_id"), row.get("loser_id"))
        if entity_id:
            out.add(entity_id)
    return out


def align_fact_receipts(
    receipts: list[str],
    bundle: EvidenceBundle,
    *,
    dropped: set[str] | None = None,
) -> list[str]:
    allowed = {canonical_id(item.source_id, (item.extra or {}).get("entity_id")) for item in bundle.items}
    blocked = dropped or set()
    kept: list[str] = []
    for line in receipts:
        text = str(line or "")
        if not text.startswith("fact:"):
            kept.append(text)
            continue
        parts = text.split(":")
        entity_id = canonical_id(parts[2] if len(parts) > 2 else "")
        if entity_id and entity_id in blocked:
            continue
        if text.startswith("fact:price:") and allowed and entity_id and entity_id not in allowed:
            continue
        kept.append(text)
    return kept
