"""High-risk amount contradiction detection across evidence text."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.evidence import EvidenceItem
from services.brain.grounding import extract
from services.brain.retrieve.conflict import detect_entity_amount_conflicts


def detect_amount_contradictions(evidence_text: str, items: list[EvidenceItem] | None = None) -> list[dict[str, Any]]:
    """Conflicting amounts only count when they belong to the same entity."""
    if items is not None:
        return detect_entity_amount_conflicts(items)
    # Blob-only callers have no entity identity; overlapping names are not a conflict.
    _ = evidence_text
    return []


def detect_phone_contradictions(evidence_text: str) -> list[dict[str, Any]]:
    phones = sorted(extract.phones(evidence_text or ""))
    if len(phones) <= 1:
        return []
    return [{"type": "phone", "values": phones, "reason": "conflicting_phones_in_evidence"}]
