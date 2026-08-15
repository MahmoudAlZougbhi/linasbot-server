"""Canonical Smart Follow-Up idempotency and credit request keys."""

from __future__ import annotations

SFU_PREFIX = "sfu:"


def canonical_sfu_key(raw: str) -> str:
    key = str(raw or "").strip()
    if not key:
        raise ValueError("idempotency_key required")
    if key.startswith(SFU_PREFIX):
        return key
    return f"{SFU_PREFIX}{key}"


def canonical_sfu_credit_request_id(raw: str) -> str:
    return canonical_sfu_key(raw)
