"""AI token metering helpers: pre-flight gate + post-usage dual-bucket debit."""

from __future__ import annotations

import logging
from typing import Any

from services.model_pricing import compute_cost_from_usage
from services.token_wallet_service import (
    InsufficientTokenBalance,
    is_unlimited_tenant,
    token_wallet_service,
)

logger = logging.getLogger(__name__)

RECHARGE_REQUIRED_MESSAGE = (
    "AI replies are paused because this workspace has no prepaid input or output tokens left. "
    "Please recharge your token wallet to continue."
)


def resolve_tenant_id(user_data: dict[str, Any] | None = None, explicit: str | None = None) -> str:
    """Resolve tenant for metering. Missing/blank tenant fails closed (no silent linas)."""
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower()
    if user_data:
        tid = user_data.get("tenant_id") or user_data.get("tenantId")
        if tid and str(tid).strip():
            return str(tid).strip().lower()
    raise ValueError("tenant_id required")


def assert_tenant_can_use_ai(tenant_id: str | None) -> None:
    """Raise InsufficientTokenBalance when either input or output bucket is empty."""
    tid = resolve_tenant_id(explicit=tenant_id)
    if is_unlimited_tenant(tid):
        return
    token_wallet_service.ensure_ai_allowed(tid, require_at_least=1)


def debit_ai_usage(
    *,
    tenant_id: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    tokens: int | None = None,
    cost_usd: float | None = None,
    input_cost_usd: float | None = None,
    output_cost_usd: float | None = None,
    model: str | None = None,
    reference: str | None = None,
) -> dict[str, Any] | None:
    """
    Debit wallet after an AI call using prompt→input and completion→output buckets.
    Unlimited tenants record usage without blocking. Empty metered wallets raise.
    """
    tid = resolve_tenant_id(explicit=tenant_id)
    use_in = max(0, int(prompt_tokens or 0))
    use_out = max(0, int(completion_tokens or 0))
    if use_in <= 0 and use_out <= 0 and tokens is not None:
        # Legacy callers that only pass total tokens.
        total = max(0, int(tokens))
        if total <= 0:
            return None
        use_in = int(round(total * 0.80))
        use_out = max(0, total - use_in)
    if use_in <= 0 and use_out <= 0:
        return None

    in_cost = float(input_cost_usd or 0.0)
    out_cost = float(output_cost_usd or 0.0)
    total_cost = float(cost_usd or 0.0)
    if (in_cost <= 0 and out_cost <= 0) and (use_in or use_out):
        priced = compute_cost_from_usage(model or "gpt-5.1", use_in, use_out)
        in_cost = float(priced["input_cost_usd"])
        out_cost = float(priced["output_cost_usd"])
        total_cost = float(priced["cost_usd"])
    elif total_cost <= 0:
        total_cost = in_cost + out_cost

    try:
        snap = token_wallet_service.debit(
            tid,
            prompt_tokens=use_in,
            completion_tokens=use_out,
            cost_usd=total_cost,
            input_cost_usd=in_cost,
            output_cost_usd=out_cost,
            reason="ai_usage",
            reference=reference,
            model=model,
        )
        return snap.to_public_dict()
    except InsufficientTokenBalance:
        logger.warning(
            "[token_wallet] debit skipped insufficient tenant=%s input=%s output=%s",
            tid,
            use_in,
            use_out,
        )
        raise
