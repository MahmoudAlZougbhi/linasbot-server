# -*- coding: utf-8 -*-
"""
Booking service mapping guards.

This module prevents cross-booking between CO2 and DPL whitening when the
model sends a mismatched service_id in create_appointment.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set

# Keep backward compatibility for older IDs while supporting current IDs.
CO2_SERVICE_IDS: Set[int] = {2, 11}
WHITENING_SERVICE_IDS: Set[int] = {5, 14}

_INTENT_PATTERNS = {
    "co2": [
        r"\bco2\b",
        r"\bscar(?:s)?\b",
        r"\bacne\s*scar(?:s)?\b",
        r"\bstretch\s*mark(?:s)?\b",
        r"ندبة|ندوب|اثر\s*حب\s*الشباب|اثار\s*حب\s*الشباب|تشققات|علامات\s*التمدد",
    ],
    "whitening": [
        r"\bdpl\b",
        r"\bwhiten(?:ing)?\b",
        r"\bdark\s*area(?:s)?\b",
        r"\bunderarm(?:s)?\b",
        r"تفتيح|تبييض|مناطق\s*غامقة|المناطق\s*الداكنة|اسوداد",
    ],
}

_INTENT_LABELS = {
    "co2": "CO2 Laser",
    "whitening": "DPL Whitening",
}


def detect_requested_service_intent(user_text: str) -> Optional[str]:
    """
    Infer requested service family from user text.

    Returns:
        - "co2" for CO2/scars-related intent
        - "whitening" for DPL/whitening-related intent
        - None when intent is missing or ambiguous
    """
    normalized_text = (user_text or "").strip().lower()
    if not normalized_text:
        return None

    hits = {"co2": 0, "whitening": 0}
    for intent, patterns in _INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized_text, re.IGNORECASE):
                hits[intent] += 1

    if hits["co2"] > 0 and hits["whitening"] == 0:
        return "co2"
    if hits["whitening"] > 0 and hits["co2"] == 0:
        return "whitening"

    # Ambiguous or no signal.
    return None


def classify_service_id(service_id: Any) -> Optional[str]:
    """Map known booking service IDs to high-level service family."""
    try:
        normalized_service_id = int(service_id)
    except (TypeError, ValueError):
        return None

    if normalized_service_id in CO2_SERVICE_IDS:
        return "co2"
    if normalized_service_id in WHITENING_SERVICE_IDS:
        return "whitening"
    return None


def service_intent_label(intent: Optional[str]) -> str:
    """Human-readable label for logs/messages."""
    if intent is None:
        return "Unknown"
    return _INTENT_LABELS.get(intent, "Unknown")


def validate_service_mapping_from_text(user_text: str, service_id: Any) -> Dict[str, Any]:
    """
    Validate that selected service_id matches requested service family.

    Only enforces hard blocking for the CO2 vs DPL whitening pair.
    """
    requested_intent = detect_requested_service_intent(user_text)
    selected_intent = classify_service_id(service_id)

    is_mismatch = (
        requested_intent in {"co2", "whitening"}
        and selected_intent in {"co2", "whitening"}
        and requested_intent != selected_intent
    )

    return {
        "is_valid": not is_mismatch,
        "is_mismatch": is_mismatch,
        "requested_intent": requested_intent,
        "selected_intent": selected_intent,
        "requested_label": service_intent_label(requested_intent),
        "selected_label": service_intent_label(selected_intent),
    }
