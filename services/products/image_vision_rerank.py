"""Vision rerank for ambiguous product image matches (billable)."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from services.model_policy import MODEL_CUSTOMER_TERRA

logger = logging.getLogger(__name__)
MAX_VISION_CANDIDATES = 8


async def vision_rerank_candidates(
    *,
    tenant_id: str,
    query_bytes: bytes,
    candidates: list[dict[str, Any]],
    media_loader: Any,
) -> dict[str, Any]:
    from services.token_metering import assert_tenant_can_use_ai, debit_ai_usage

    bounded = candidates[:MAX_VISION_CANDIDATES]
    if not bounded:
        return {"resolved": False, "product_id": None, "confidence": "none"}

    assert_tenant_can_use_ai(tenant_id)
    content_parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Customer sent a product image. Pick the best matching catalog candidate or none. "
                "Return JSON only: {\"product_id\": \"...\"|null, \"confidence\": \"high|medium|low\"}."
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(query_bytes).decode('ascii')}"},
        },
    ]
    catalog: list[dict[str, str]] = []
    for cand in bounded:
        product_id = str(cand.get("product_id") or "")
        media_id = str(cand.get("media_id") or "")
        title = str(cand.get("product_name") or product_id)
        raw = media_loader(media_id=media_id)
        if raw is None:
            continue
        catalog.append({"product_id": product_id, "title": title, "media_id": media_id})
        content_parts.append({"type": "text", "text": f"Candidate {product_id}: {title}"})
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(raw).decode('ascii')}"},
            }
        )
    if not catalog:
        return {"resolved": False, "product_id": None, "confidence": "none"}

    from services.llm_core_service import build_chat_completion_kwargs, client

    messages = [{"role": "user", "content": content_parts}]
    kwargs = build_chat_completion_kwargs(
        model=MODEL_CUSTOMER_TERRA,
        messages=messages,
        max_tokens=200,
        temperature=0.0,
        reasoning_effort="none",
    )
    kwargs["messages"] = messages
    response = await client.chat.completions.create(**kwargs)
    usage = getattr(response, "usage", None)
    try:
        debit_ai_usage(
            tenant_id=tenant_id,
            model=MODEL_CUSTOMER_TERRA,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            reference="product_image_candidate_rerank",
        )
    except Exception:
        logger.exception("product_image_candidate_rerank_debit_failed tenant=%s", tenant_id)

    parsed = _parse_json((response.choices[0].message.content or "").strip())
    product_id = str(parsed.get("product_id") or "").strip() or None
    confidence = str(parsed.get("confidence") or "low").strip().lower()
    if product_id and product_id not in {c["product_id"] for c in catalog}:
        product_id = None
    if confidence != "high":
        product_id = None
    return {"resolved": bool(product_id), "product_id": product_id, "confidence": confidence}


def _parse_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            loaded = json.loads(text[start : end + 1])
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
