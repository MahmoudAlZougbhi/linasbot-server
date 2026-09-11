"""Controlled live OpenAI agent turns for Customer Brain lab (no secret printing)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from services.customer_ai.generate.reply import openai_configured

GateFn = Callable[..., dict[str, Any]]

_CASES: tuple[dict[str, str], ...] = (
    {"id": "faq_en", "message": "What is your refund policy?", "lang": "en"},
    {"id": "price_ar", "message": "شو سعر إزالة الشعر بالليزر أنطلياس؟", "lang": "ar"},
    {"id": "hours_en", "message": "What are Antelias branch hours on Monday?", "lang": "en"},
    {"id": "branch_fr", "message": "Quelle est l'adresse de la branche Verdun?", "lang": "fr"},
    {"id": "arabizi", "message": "badek price laser antelias?", "lang": "arabizi"},
    {"id": "unsupported_book", "message": "Book me tomorrow at 3pm for laser", "lang": "en"},
    {"id": "handoff", "message": "I want to talk to a human agent please", "lang": "en"},
)


async def openai_agent_live(gate: GateFn, *, tenant_id: str) -> dict[str, Any]:
    if not openai_configured():
        return gate("BLOCKED", "OPENAI_API_KEY missing — BLOCKED_BY_SECRET")

    from services.customer_ai.runtime import run_customer_ai_dm

    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    failures: list[str] = []
    for case in _CASES:
        conversation_id = f"lab-openai-{case['id']}-{uuid.uuid4().hex[:10]}"
        user_id = f"lab-user-{case['id']}"
        message_id = f"lab-msg-{uuid.uuid4().hex[:12]}"
        t0 = time.perf_counter()
        try:
            outcome = await run_customer_ai_dm(
                tenant_id=tenant_id,
                message=case["message"],
                channel="instagram_dm",
                conversation_id=conversation_id,
                user_id=user_id,
                message_id=message_id,
                apply_customer_usage_limits=False,
                response_language=case.get("lang") or "",
            )
        except Exception as exc:  # noqa: BLE001 — lab harness records provider/runtime faults
            latencies.append(time.perf_counter() - t0)
            failures.append(f"{case['id']}:exc:{type(exc).__name__}")
            rows.append({"id": case["id"], "status": "FAIL", "error": type(exc).__name__})
            continue
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)
        meta = outcome.metadata if isinstance(outcome.metadata, dict) else {}
        reply = (outcome.reply or "").strip()
        ai_called = bool(meta.get("ai_called"))
        stop = bool(outcome.stop)
        reason = str(outcome.reason or "")
        ok = False
        if case["id"] == "unsupported_book":
            # Must not invent a confirmed booking; empty/stop or clear unsupported is OK.
            lowered = reply.lower()
            hallucinated = any(tok in lowered for tok in ("confirmed", "booked you", "reservation id"))
            ok = (not hallucinated) and (stop or bool(reply))
        elif case["id"] == "handoff":
            ok = stop or "human" in reply.lower() or "agent" in reply.lower() or bool(reply)
        else:
            ok = (not stop and bool(reply) and ai_called) or (bool(reply) and not stop)
        if not ok:
            failures.append(f"{case['id']}:stop={stop}:ai={ai_called}:reason={reason[:40]}")
        rows.append(
            {
                "id": case["id"],
                "status": "PASS" if ok else "FAIL",
                "stop": stop,
                "ai_called": ai_called,
                "reason": reason[:80],
                "reply_len": len(reply),
                "latency_sec": round(elapsed, 3),
            }
        )

    from services.customer_ai.evals.metrics import percentile

    passed = sum(1 for r in rows if r.get("status") == "PASS")
    status = "PASS" if passed == len(_CASES) and not failures else "FAIL"
    if not rows:
        status = "FAIL"
    return gate(
        status,
        f"live_turns={passed}/{len(_CASES)}",
        cases=rows,
        failures=failures,
        latency_p50=round(percentile(latencies, 0.5), 3) if latencies else None,
        latency_p95=round(percentile(latencies, 0.95), 3) if latencies else None,
        latency_p99=round(percentile(latencies, 0.99), 3) if latencies else None,
    )
