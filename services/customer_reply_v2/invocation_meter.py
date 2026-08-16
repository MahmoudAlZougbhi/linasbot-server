"""Per-invocation AI metering for a customer turn (no Plan/UI changes)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def new_customer_turn_id() -> str:
    return uuid.uuid4().hex


@dataclass
class InvocationRecord:
    operation: str
    provider: str = "openai"
    model: str = ""
    requested_reasoning_effort: str | None = None
    effective_reasoning_effort: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    tool_rounds: int = 0
    repair: bool = False
    provider_cost_usd: float | None = None
    latency_ms: float | None = None
    success: bool = True
    failure_stage: str | None = None


@dataclass
class CustomerTurnMeter:
    tenant_id: str
    customer_turn_id: str = field(default_factory=new_customer_turn_id)
    invocations: list[InvocationRecord] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    def record(self, inv: InvocationRecord) -> InvocationRecord:
        self.invocations.append(inv)
        return inv

    def to_public_dict(self) -> dict[str, Any]:
        rows = []
        for inv in self.invocations:
            rows.append(
                {
                    "tenant_id": self.tenant_id,
                    "customer_turn_id": self.customer_turn_id,
                    "operation": inv.operation,
                    "provider": inv.provider,
                    "model": inv.model,
                    "requested_reasoning_effort": inv.requested_reasoning_effort,
                    "effective_reasoning_effort": inv.effective_reasoning_effort,
                    "input_tokens": inv.input_tokens,
                    "cached_input_tokens": inv.cached_input_tokens,
                    "output_tokens": inv.output_tokens,
                    "reasoning_tokens": inv.reasoning_tokens,
                    "tool_rounds": inv.tool_rounds,
                    "repair": inv.repair,
                    "provider_cost_usd": inv.provider_cost_usd,
                    "latency_ms": inv.latency_ms,
                    "success": inv.success,
                    "failure_stage": inv.failure_stage,
                }
            )
        return {
            "customer_turn_id": self.customer_turn_id,
            "tenant_id": self.tenant_id,
            "invocations": rows,
            "ai_invocation_count": len(rows),
            "latency_ms": (time.perf_counter() - self.started) * 1000,
        }


def effort_pair(*, requested: str | None, effective: str | None) -> dict[str, str | None]:
    """Never report requested as effective when the provider clamped the value."""
    return {
        "requested_reasoning_effort": requested,
        "effective_reasoning_effort": effective,
    }
