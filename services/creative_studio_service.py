"""Creative Studio workflows — uses CM context + provider router + credit ledger."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from services.credit_ledger_service import credit_ledger_service
from services.entitlements_service import assert_feature
from services.providers.router import provider_router

CreativeKind = Literal["post", "caption", "image", "reel_concept", "video", "rewrite", "campaign_ideas"]


def _cm_brand_context(tenant_id: str) -> str:
    try:
        from services.cm.storage import get_draft

        parts: list[str] = []
        for section in ("ai_basics", "style", "services", "prices", "restricted"):
            env = get_draft(section, tenant_id=tenant_id, create_default=False)
            if env is None:
                continue
            parts.append(f"## {section}\n{env.payload}")
        return "\n\n".join(parts)[:12000]
    except Exception:
        return ""


async def create_creative_draft(
    *,
    tenant_id: str,
    user_id: str,
    kind: CreativeKind,
    prompt: str,
) -> dict[str, Any]:
    assert_feature(tenant_id, "creative_studio")
    request_id = uuid.uuid4().hex
    # Image/video are high-cost: reserve credits first.
    reserve_credits = 40 if kind == "image" else 200 if kind == "video" else 8
    reservation_id = credit_ledger_service.reserve(
        tenant_id=tenant_id,
        user_id=user_id,
        credits=reserve_credits,
        operation_type=f"creative_{kind}",
        request_id=request_id,
    )
    context = _cm_brand_context(tenant_id)
    try:
        if kind in {"image", "video"}:
            from services.job_queue import job_queue

            job = job_queue.enqueue(
                queue="expensive",
                job_type=f"creative_{kind}",
                tenant_id=tenant_id,
                payload={
                    "kind": kind,
                    "prompt": prompt,
                    "reservation_id": reservation_id,
                    "user_id": user_id,
                },
                idempotency_key=f"creative:{kind}:{request_id}",
                reservation_id=reservation_id,
            )
            return {
                "status": "queued",
                "job_id": job.id,
                "reservation_id": reservation_id,
                "kind": kind,
            }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Linas AI Creative Studio. Use the tenant brand context. "
                    "Respect restrictions. Do not invent prices or medical claims.\n\n"
                    f"{context}"
                ),
            },
            {"role": "user", "content": f"Create a {kind}: {prompt}"},
        ]
        result = await provider_router.generate_text(kind="creative_text", messages=messages)
        credit_ledger_service.capture(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            provider_cost_usd=result.provider_cost_usd,
            model_provider=f"{result.provider}:{result.model}",
        )
        return {
            "status": "completed",
            "kind": kind,
            "text": result.text,
            "model": result.model,
            "provider_cost_usd": result.provider_cost_usd,
            "reservation_id": reservation_id,
        }
    except Exception:
        credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
        raise
