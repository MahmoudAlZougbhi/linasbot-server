"""Split remaining credits into membership vs purchased.

Spend included (membership) first. Purchased credits persist after the period grant.
The ledger is one pool; this is the product-facing remaining split.
"""

from __future__ import annotations


def split_credit_remaining(
    *,
    included: int,
    purchased: int,
    available: int,
    reserved: int = 0,
) -> dict[str, int]:
    included_n = max(0, int(included or 0))
    purchased_n = max(0, int(purchased or 0))
    available_n = max(0, int(available or 0))
    reserved_n = max(0, int(reserved or 0))
    pool = included_n + purchased_n
    used = max(0, pool - available_n - reserved_n) if pool > 0 else 0
    membership = included_n - min(used, included_n)
    if membership > available_n:
        membership = available_n
    return {
        "membership_credits_remaining": membership,
        "purchased_credits_remaining": available_n - membership,
        "credits_used": used,
    }
