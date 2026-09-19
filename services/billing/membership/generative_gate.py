"""Customer generative eligibility — message ledger."""

from __future__ import annotations


def generative_block_reason(tenant_id: str, *, honor_inflight_reserved: bool = False) -> str | None:
    tid = (tenant_id or "").strip()
    if not tid:
        return "unpublished"
    from services.billing.credit_ai_gate import ai_generation_blocked

    if ai_generation_blocked(tid, honor_inflight_reserved=honor_inflight_reserved):
        return "insufficient_messages"
    return None


def generative_ai_blocked(tenant_id: str, *, honor_inflight_reserved: bool = False) -> bool:
    return generative_block_reason(tenant_id, honor_inflight_reserved=honor_inflight_reserved) is not None
