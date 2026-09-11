"""Customer Brain security helpers."""

from __future__ import annotations

from services.customer_ai.security.injection import evidence_has_injection, sanitize_evidence_for_prompt

__all__ = ["evidence_has_injection", "sanitize_evidence_for_prompt"]
