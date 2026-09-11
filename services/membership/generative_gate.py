"""Customer generative eligibility. Credits stay until message billing is on."""

from __future__ import annotations


def generative_block_reason(tenant_id: str, *, honor_inflight_reserved: bool = False) -> str | None:
    """Return a stop reason when the next Customer AI turn cannot start."""
    tid = (tenant_id or "").strip()
    if not tid:
        return "unpublished"
    from services.membership.message_flags import message_billing_enabled

    if message_billing_enabled():
        from services.membership.message_ledger import can_start_generative
        from services.membership.pg_store import MessageStoreUnavailable

        try:
            if not can_start_generative(tid):
                return "insufficient_messages"
        except MessageStoreUnavailable:
            return "insufficient_messages"
        except Exception:
            return "insufficient_messages"
        return None
    from services.credit_ai_gate import ai_generation_blocked

    if ai_generation_blocked(tid, honor_inflight_reserved=honor_inflight_reserved):
        return "insufficient_credits"
    return None


def generative_ai_blocked(tenant_id: str, *, honor_inflight_reserved: bool = False) -> bool:
    return generative_block_reason(tenant_id, honor_inflight_reserved=honor_inflight_reserved) is not None
