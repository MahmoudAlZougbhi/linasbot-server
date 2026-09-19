"""AI pre-flight uses the message ledger. Token wallet is not a live meter."""

from __future__ import annotations

from typing import Any

RECHARGE_REQUIRED_MESSAGE = (
    "AI replies are paused because this workspace has no messages left. "
    "Please buy messages or upgrade the plan to continue."
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
    """Raise when remaining messages is 0. Token wallet is not a live gate."""
    tid = resolve_tenant_id(explicit=tenant_id)
    from services.billing.membership.generative_gate import generative_ai_blocked

    if generative_ai_blocked(tid):
        raise PermissionError("Insufficient messages")


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
    """Token-wallet debit is not a live meter. Credits are captured on the ledger."""
    _ = (
        tenant_id,
        prompt_tokens,
        completion_tokens,
        tokens,
        cost_usd,
        input_cost_usd,
        output_cost_usd,
        model,
        reference,
    )
    return None
