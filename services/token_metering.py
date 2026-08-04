"""AI token metering helpers: pre-flight gate + post-usage debit."""

from __future__ import annotations

import logging
from typing import Any

from services.token_wallet_service import (
    InsufficientTokenBalance,
    is_unlimited_tenant,
    token_wallet_service,
)

logger = logging.getLogger(__name__)

RECHARGE_REQUIRED_MESSAGE = (
    "AI replies are paused because this workspace has no prepaid tokens left. "
    "Please recharge your token wallet to continue."
)


def resolve_tenant_id(user_data: dict[str, Any] | None = None, explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower()
    if user_data:
        tid = user_data.get("tenant_id") or user_data.get("tenantId")
        if tid:
            return str(tid).strip().lower()
    return "linas"


def assert_tenant_can_use_ai(tenant_id: str | None) -> None:
    """Raise InsufficientTokenBalance when metered tenant balance is empty."""
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
    model: str | None = None,
    reference: str | None = None,
) -> dict[str, Any] | None:
    """
    Debit wallet after an AI call using the same token accounting as Interaction Logs.
    Unlimited tenants record usage without blocking. Empty metered wallets raise.
    """
    tid = resolve_tenant_id(explicit=tenant_id)
    total = 0
    if tokens is not None:
        total = max(0, int(tokens))
    else:
        total = max(0, int(prompt_tokens or 0)) + max(0, int(completion_tokens or 0))
    if total <= 0:
        return None
    try:
        snap = token_wallet_service.debit(
            tid,
            total,
            cost_usd=float(cost_usd or 0.0),
            reason="ai_usage",
            reference=reference,
            model=model,
        )
        return snap.to_public_dict()
    except InsufficientTokenBalance:
        # Race: balance hit zero mid-call. Record nothing further; caller already generated.
        # Future calls fail at pre-flight. Do not go negative.
        logger.warning("[token_wallet] debit skipped insufficient tenant=%s tokens=%s", tid, total)
        raise
