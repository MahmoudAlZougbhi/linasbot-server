"""Lab/shadow Brain compare — never sends customer messages or bills."""

from __future__ import annotations

import os
from typing import Any


def shadow_mode_enabled() -> bool:
    raw = (os.getenv("CUSTOMER_BRAIN_SHADOW_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def shadow_compare_payload(
    *,
    authoritative: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a non-delivery comparison record for Lab/diagnostics."""
    left = authoritative or {}
    right = shadow or {}
    return {
        "shadow_mode": True,
        "delivered_from": "authoritative",
        "customer_message_sent_from_shadow": False,
        "billing_from_shadow": False,
        "authoritative_decision": left.get("decision"),
        "shadow_decision": right.get("decision"),
        "authoritative_evidence_ids": list(left.get("evidence_ids") or []),
        "shadow_evidence_ids": list(right.get("evidence_ids") or []),
        "latency_ms": {
            "authoritative": left.get("latency_ms"),
            "shadow": right.get("latency_ms"),
        },
    }
