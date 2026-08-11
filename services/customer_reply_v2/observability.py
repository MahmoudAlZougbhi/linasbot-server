"""Safe structured telemetry for Customer Reply AI V2 (no raw conversations/secrets)."""

from __future__ import annotations

import hashlib
import time
from typing import Any


def hash_tenant(tenant_id: str) -> str:
    return hashlib.sha256((tenant_id or "").encode()).hexdigest()[:12]


def build_safe_trace(
    *,
    tenant_id: str,
    channel: str,
    published_revision: str,
    faq_category: str,
    retrieval_rounds: int,
    selected_source_ids: list[str],
    evidence_status: str,
    validation_ok: bool | None,
    repair_attempts: int,
    requested_models: dict[str, str],
    returned_models: dict[str, str],
    context_message_count: int,
    context_compacted: bool,
    delivery_result: str,
    latency_ms: float | None = None,
    stage: str = "answer",
    reasoning_effort: dict[str, str] | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """Privacy-safe trace: stage, models, effort, channel, tenant hash, tokens/cost — no secrets."""
    return {
        "trace_id": hashlib.sha256(f"{time.time_ns()}:{tenant_id}:{channel}".encode()).hexdigest()[:16],
        "tenant_hash": hash_tenant(tenant_id),
        "channel": channel,
        "stage": stage,
        "published_revision": published_revision,
        "faq_category": faq_category,
        "retrieval_rounds": retrieval_rounds,
        "selected_source_ids": list(selected_source_ids)[:40],
        "evidence_status": evidence_status,
        "validation_ok": validation_ok,
        "repair_attempts": repair_attempts,
        "requested_models": requested_models,
        "returned_models": returned_models,
        "reasoning_effort": reasoning_effort or {},
        "context_message_count": context_message_count,
        "context_compacted": context_compacted,
        "delivery_result": delivery_result,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "classic_fallback": False,
    }
