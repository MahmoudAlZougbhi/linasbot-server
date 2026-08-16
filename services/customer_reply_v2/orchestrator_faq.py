"""FAQ direct-reply outcome + metering for Customer Reply V2."""

from __future__ import annotations

import time
from typing import Any

from services.customer_reply_v2.faq_eligibility import FaqTurnGuards
from services.customer_reply_v2.faq_fast_path import FaqFastPathResult, try_faq_fast_path
from services.customer_reply_v2.flags import flags_snapshot
from services.customer_reply_v2.invocation_meter import CustomerTurnMeter, InvocationRecord
from services.customer_reply_v2.observability import build_safe_trace
from services.customer_reply_v2.open_drafts import has_open_collecting_draft


def faq_direct_invocation() -> InvocationRecord:
    return InvocationRecord(
        operation="faq_direct_reply",
        provider="none",
        model="",
        requested_reasoning_effort=None,
        effective_reasoning_effort=None,
        success=True,
        is_ai=False,
    )


def build_faq_guards(
    *,
    tenant_id: str,
    customer_id: str,
    channel: str,
    attachment_types: list[str] | None,
    reply_to: str,
    has_unresolved_context_refs: bool,
    has_ai_guidance_comment_rule: bool = False,
    detected_language: str = "",
    response_language: str = "",
) -> FaqTurnGuards:
    attachments = [str(a).strip() for a in (attachment_types or []) if str(a).strip()]
    return FaqTurnGuards(
        has_attachment=bool(attachments),
        has_reply_to=bool(str(reply_to or "").strip()),
        has_open_draft=has_open_collecting_draft(tenant_id=tenant_id, customer_id=customer_id),
        has_ai_guidance_comment_rule=has_ai_guidance_comment_rule,
        has_unresolved_context_refs=has_unresolved_context_refs,
        channel=channel,
        response_language=response_language,
        detected_language=detected_language,
    )


async def evaluate_faq_turn(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    response_language: str,
    channel: str,
    customer_id: str,
    attachment_types: list[str] | None = None,
    reply_to: str = "",
    has_unresolved_context_refs: bool = False,
    has_ai_guidance_comment_rule: bool = False,
) -> FaqFastPathResult:
    guards = build_faq_guards(
        tenant_id=tenant_id,
        customer_id=customer_id,
        channel=channel,
        attachment_types=attachment_types,
        reply_to=reply_to,
        has_unresolved_context_refs=has_unresolved_context_refs,
        has_ai_guidance_comment_rule=has_ai_guidance_comment_rule,
        detected_language=detected_language,
        response_language=response_language,
    )
    return await try_faq_fast_path(
        tenant_id=tenant_id,
        message=message,
        detected_language=detected_language,
        response_language=response_language,
        has_unresolved_context_refs=has_unresolved_context_refs,
        guards=guards,
        channel=channel,
    )


def faq_trace_fields(faq: FaqFastPathResult) -> dict[str, Any]:
    meta = dict(faq.metadata or {})
    return {
        "faq_checked": bool(faq.checked),
        "faq_match_id": meta.get("faq_id") or "",
        "faq_match_score": meta.get("match_score"),
        "faq_direct_reply": bool(faq.hit),
        "faq_match_type": meta.get("match_type") or faq.reason,
        "faq_revision": meta.get("faq_revision") or "",
    }


def faq_direct_outcome_kwargs(
    *,
    tenant_id: str,
    channel: str,
    revision: str,
    faq: FaqFastPathResult,
    started: float,
    extra_metadata: dict[str, Any] | None = None,
    meter: CustomerTurnMeter | None = None,
    context_message_count: int = 0,
    context_compacted: bool = False,
) -> dict[str, Any]:
    if meter is not None:
        meter.record(faq_direct_invocation())
    meta = dict(faq.metadata or {})
    trace = build_safe_trace(
        tenant_id=tenant_id,
        channel=channel,
        published_revision=revision,
        faq_category=faq.reason,
        retrieval_rounds=0,
        selected_source_ids=[f"faq:{meta.get('faq_id')}"] if meta.get("faq_id") else [],
        evidence_status="faq_hit",
        validation_ok=True,
        repair_attempts=0,
        requested_models={},
        returned_models={},
        context_message_count=context_message_count,
        context_compacted=context_compacted,
        delivery_result="faq_reply",
        latency_ms=(time.perf_counter() - started) * 1000,
        stage="faq",
        faq_checked=True,
        faq_match_id=str(meta.get("faq_id") or ""),
        faq_match_score=meta.get("match_score"),
        faq_direct_reply=True,
    )
    metadata: dict[str, Any] = {
        "faq": meta,
        "trace": {**trace, **faq_trace_fields(faq)},
        "flags": flags_snapshot(),
        "ai_called": False,
        "cost_status": "none",
        "faq_direct_reply": True,
        "luna_called": False,
        "tera_called": False,
    }
    if meter is not None:
        metadata["metering"] = meter.to_public_dict()
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "stop": True,
        "reply": faq.answer,
        "reason": faq.reason,
        "evidence_status": "faq_hit",
        "metadata": metadata,
    }
