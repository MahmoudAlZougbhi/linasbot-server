"""One inbound-DM orchestrator: fingerprint match → product evidence, else vision RAG.

Terra still authors customer copy. This module only attaches EVIDENCE ids/cards.
"""

from __future__ import annotations

from typing import Any

from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.turn import CustomerTurn
from services.products.image_match import high_confidence_matches


def attach_inbound_product_image_match(tenant_id: str, blob: bytes, result: Any) -> bool:
    """Stamp high-confidence product ids on the inbound result. True when evidence should skip vision."""
    matches = high_confidence_matches(tenant_id, blob)
    payload = [{"product_id": row["product_id"], "score": row["score"]} for row in matches]
    if hasattr(result, "product_image_matches"):
        result.product_image_matches = payload
    return bool(payload)


def merge_product_image_evidence(turn: CustomerTurn, bundle: EvidenceBundle) -> EvidenceBundle:
    """Prepend hydrated product cards from inbound image match. Never authors reply text."""
    extra = turn.extra if isinstance(turn.extra, dict) else {}
    raw = extra.get("product_image_matches")
    rows: list[Any] = raw if isinstance(raw, list) else []
    ids = [str(row.get("product_id") or "").strip() for row in rows if isinstance(row, dict)]
    ids = [pid for pid in ids if pid]
    if not ids:
        return bundle
    from services.brain.retrieve.products_hydrate import evidence_for_product_ids

    incoming = evidence_for_product_ids(
        turn.tenant_id,
        ids,
        extra={"product_image_match": True},
    )
    if not incoming:
        return bundle
    merged = _merge_items(incoming, list(bundle.items))
    return bundle.model_copy(update={"items": merged, "outcome": "found"})


def _merge_items(incoming: list[EvidenceItem], existing: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[str] = set()
    out: list[EvidenceItem] = []
    for item in [*incoming, *existing]:
        key = item.evidence_id or f"{item.source_family}:{item.source_id}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
