"""Luna title resolver — fallback after deterministic product search fails.

Sends product titles only (never descriptions, images, or prices).
Chunks large catalogs so every active title is compared.
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

MAX_MATCHES = 5
TITLES_PER_CHUNK = 80


async def resolve_product_titles_with_luna(
    session: Session,
    *,
    tenant_id: str,
    query: str,
    limit: int = MAX_MATCHES,
    alternate_queries: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Pick best product title matches using Luna when deterministic search found nothing."""
    from services.token_metering import assert_tenant_can_use_ai, debit_ai_usage

    query_text = str(query or "").strip()
    extras = [str(q).strip() for q in (alternate_queries or []) if str(q).strip()]
    if extras:
        query_text = json.dumps({"original_query": query_text, "alternate_queries": extras}, ensure_ascii=False)
    if not query_text:
        return []

    repo = ProductsRepository(session)
    rows = repo.list_all_for_tenant(tenant_id=tenant_id, customer_facing=True)
    if not rows:
        return []

    assert_tenant_can_use_ai(tenant_id)

    all_ids: list[str] = []
    total_prompt = 0
    total_completion = 0
    for start in range(0, len(rows), TITLES_PER_CHUNK):
        chunk = rows[start : start + TITLES_PER_CHUNK]
        chunk_ids, prompt_toks, completion_toks = await _luna_match_chunk(
            tenant_id=tenant_id,
            query_text=query_text,
            rows=chunk,
            limit=limit,
        )
        total_prompt += prompt_toks
        total_completion += completion_toks
        for pid in chunk_ids:
            if pid not in all_ids:
                all_ids.append(pid)
        if len(all_ids) >= limit:
            break

    try:
        debit_ai_usage(
            tenant_id=tenant_id,
            model=MODEL_CUSTOMER_LUNA,
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            reference="product_title_resolution_fallback",
        )
    except Exception:
        logger.exception("products_luna_title_debit_failed tenant=%s", tenant_id)

    by_id = {row.id: row for row in rows}
    out: list[dict[str, Any]] = []
    for pid in all_ids:
        row = by_id.get(pid)
        if row is not None:
            out.append(product_to_dict(row))
        if len(out) >= limit:
            break
    return out


async def _luna_match_chunk(
    *,
    tenant_id: str,
    query_text: str,
    rows: list[Any],
    limit: int,
) -> tuple[list[str], int, int]:
    titles = [
        {
            "product_id": row.id,
            "title": row.name,
            "original_title": row.name,
            "description": str(getattr(row, "description", "") or "")[:180],
            "ai_search_title": str(getattr(row, "ai_search_title", "") or ""),
            "ai_search_description": str(getattr(row, "ai_search_description", "") or ""),
            "ai_search_keywords": list(getattr(row, "ai_search_keywords", None) or [])[:8],
        }
        for row in rows
    ]
    system = (
        "You resolve a customer product query against a catalog page. "
        "Each row has original_title, owner description, and English search hints. "
        "Search hints are not business facts. Never invent products. "
        'Return JSON only: {"product_ids": ["id", ...]} with at most '
        f"{min(limit, MAX_MATCHES)} best matches. Exclude products not in the list. "
        "Use original_query and any alternate_queries together; never drop the original wording."
    )
    user = json.dumps({"query": query_text, "titles": titles}, ensure_ascii=False)

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
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    content = (response.choices[0].message.content or "").strip()
    return _parse_product_ids(content), prompt_tokens, completion_tokens


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
