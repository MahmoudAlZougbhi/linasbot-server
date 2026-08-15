"""Luna title resolver — bounded fallback after deterministic product search fails.

Sends product titles only (never descriptions, images, or prices).
Metered via existing token_metering; 0 credits blocks via credit_ai_gate.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from services.model_policy import MODEL_CUSTOMER_LUNA
from services.products.repository import ProductsRepository
from services.products.schemas import product_to_dict

logger = logging.getLogger(__name__)

MAX_TITLE_CANDIDATES = 80
MAX_MATCHES = 5


async def resolve_product_titles_with_luna(
    session: Session,
    *,
    tenant_id: str,
    query: str,
    limit: int = MAX_MATCHES,
) -> list[dict[str, Any]]:
    """Pick best product title matches using Luna when deterministic search found nothing."""
    from services.token_metering import assert_tenant_can_use_ai, debit_ai_usage

    query_text = str(query or "").strip()
    if not query_text:
        return []

    repo = ProductsRepository(session)
    rows = repo.list_all_for_tenant(tenant_id=tenant_id)[:MAX_TITLE_CANDIDATES]
    if not rows:
        return []

    titles = [{"product_id": row.id, "title": row.name} for row in rows]
    system = (
        "You resolve a customer product title query against a bounded catalog title list. "
        "Return JSON only: {\"product_ids\": [\"id\", ...]} with at most "
        f"{min(limit, MAX_MATCHES)} best matches. Titles only — never invent products."
    )
    user = json.dumps({"query": query_text, "titles": titles}, ensure_ascii=False)

    assert_tenant_can_use_ai(tenant_id)

    from services.llm_core_service import build_chat_completion_kwargs, client

    kwargs = build_chat_completion_kwargs(
        model=MODEL_CUSTOMER_LUNA,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=400,
        temperature=0.0,
        reasoning_effort="none",
    )
    response = await client.chat.completions.create(**kwargs)
    usage = getattr(response, "usage", None)
    try:
        debit_ai_usage(
            tenant_id=tenant_id,
            model=MODEL_CUSTOMER_LUNA,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            reference="products_luna_title_resolver",
        )
    except Exception:
        logger.exception("products_luna_title_debit_failed tenant=%s", tenant_id)

    content = (response.choices[0].message.content or "").strip()
    product_ids = _parse_product_ids(content)
    if not product_ids:
        return []

    by_id = {row.id: row for row in rows}
    out: list[dict[str, Any]] = []
    for pid in product_ids:
        row = by_id.get(pid)
        if row is not None:
            out.append(product_to_dict(row))
        if len(out) >= limit:
            break
    return out


def _parse_product_ids(content: str) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, dict):
        return []
    ids = parsed.get("product_ids") or parsed.get("matches") or []
    if not isinstance(ids, list):
        return []
    return [str(i).strip() for i in ids if str(i).strip()]
