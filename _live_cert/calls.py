"""Shared live-cert helpers. Import only after bootstrap.configure()."""

from __future__ import annotations

import time
from typing import Any

from _live_cert.bootstrap import TENANT_ID

RESULTS: list[dict[str, Any]] = []


def trace(out: Any, *, message: str, channel: str) -> dict[str, Any]:
    meta = dict(getattr(out, "metadata", None) or {})
    metering = dict(meta.get("metering") or {})
    ops = [str(row.get("operation") or "") for row in metering.get("invocations") or []]
    return {
        "message": message,
        "channel": channel,
        "reason": getattr(out, "reason", None),
        "reply": getattr(out, "reply", None),
        "error": getattr(out, "error", None),
        "faq_direct": meta.get("faq_direct_reply"),
        "luna_called": "luna_retrieval" in ops,
        "tera_called": any(str(op).startswith("tera_") for op in ops),
        "selected_source_ids": list(meta.get("selected_source_ids") or []),
        "tool_trace": list(meta.get("tool_trace") or []),
        "luna_recommended_tera_effort": meta.get("luna_recommended_tera_effort"),
        "retrieval_requested": meta.get("requested_reasoning_effort_retrieval")
        or meta.get("reasoning_effort_retrieval"),
        "retrieval_effective": meta.get("reasoning_effort_retrieval"),
        "answer_requested": meta.get("requested_reasoning_effort_answer"),
        "answer_effective": meta.get("reasoning_effort_answer"),
        "media_actions": meta.get("media_actions") or [],
        "media_delivery": meta.get("media_delivery") or {},
        "resource_actions": meta.get("resource_actions") or [],
        "resource_delivery": meta.get("resource_delivery") or {},
        "draft_result": meta.get("draft_result") or {},
        "comment_rule_id": meta.get("comment_rule_id"),
        "comment_rule_mode": meta.get("comment_rule_mode"),
        "comment_rule_action": meta.get("comment_rule_action"),
        "metering": metering,
        "prompt_tokens": meta.get("prompt_tokens"),
        "cost_status": meta.get("cost_status"),
        "ai_called": meta.get("ai_called"),
        "claimed_sent": bool((meta.get("resource_delivery") or {}).get("claimed_sent")),
    }


def record(name: str, label: str, **kwargs: Any) -> dict[str, Any]:
    row = {"name": name, "label": label, **kwargs}
    RESULTS.append(row)
    print(f"[{label}] {name}: {row.get('ok')} {row.get('reason') or row.get('blocker') or ''}", flush=True)
    return row


def _failed(exc: BaseException) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        reply=None,
        reason="exception",
        error=f"{type(exc).__name__}: {exc}"[:500],
        metadata={},
    )


async def dm(message: str, **kwargs: Any) -> Any:
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    try:
        return await run_customer_reply_v2_dm(
            tenant_id=TENANT_ID,
            message=message,
            detected_language=kwargs.pop("detected_language", "ar"),
            response_language=kwargs.pop("response_language", "ar"),
            channel=kwargs.pop("channel", "instagram_dm"),
            provider_sender_id=kwargs.pop("provider_sender_id", "v10_cust"),
            conversation_id=kwargs.pop("conversation_id", "v10_conv"),
            injected_history=kwargs.pop("injected_history", []),
            apply_customer_usage_limits=False,
            **kwargs,
        )
    except Exception as exc:
        return _failed(exc)


async def comment(text: str, **kwargs: Any) -> Any:
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    try:
        return await run_customer_reply_v2_comment(
            tenant_id=TENANT_ID,
            comment_text=text,
            detected_language=kwargs.pop("detected_language", "ar"),
            response_language=kwargs.pop("response_language", "ar"),
            channel=kwargs.pop("channel", "instagram_comment"),
            provider_sender_id=kwargs.pop("provider_sender_id", "v10_cmt"),
            post_id=kwargs.pop("post_id", "POST_GENERIC"),
            comment_id=kwargs.pop("comment_id", "cmt1"),
            **kwargs,
        )
    except Exception as exc:
        return _failed(exc)


def has_price(reply: str | None) -> bool:
    text = reply or ""
    return "299" in text and "invent" not in text.lower()


async def probe_openai(key: str) -> dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=key)
    t0 = time.perf_counter()
    models = await client.models.list()
    ids = sorted({m.id for m in models.data})
    want = ["gpt-5.6-luna", "gpt-5.6-terra", "text-embedding-3-small", "gpt-4o-transcribe"]
    present = {m: m in ids for m in want}
    embed = await client.embeddings.create(model="text-embedding-3-small", input="v10 live cert ping")
    usage = getattr(embed, "usage", None)
    return {
        "ok": True,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "models_present": present,
        "embedding_dim": len(embed.data[0].embedding),
        "embed_tokens": getattr(usage, "total_tokens", None) if usage else None,
        "model_count": len(ids),
    }
