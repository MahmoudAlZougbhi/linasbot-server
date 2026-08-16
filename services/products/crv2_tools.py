"""Customer Reply V2 product tools — tenant injected server-side."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from services.products.active_context import get_active_product, set_active_product
from services.products.availability import is_customer_searchable
from services.products.details_for_tera import product_details_for_tera
from services.products.image_index import find_image_candidates
from services.products.image_vision_rerank import vision_rerank_candidates
from services.products.media import load_media_bytes, load_media_meta
from services.products.reply_to_map import resolve_reply_to_product
from services.products.repository import ProductsRepository
from services.products.search import search_product_by_title
from services.products.title_pages import list_active_product_titles, slim_product_match

SIMILARITY_THRESHOLD = float(os.getenv("LINAS_PRODUCT_IMAGE_SIMILARITY_THRESHOLD", "0.85"))
TOP_K_DEFAULT = int(os.getenv("LINAS_PRODUCT_IMAGE_TOP_K", "8"))


def _run_async(coro: Any) -> Any:
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=45)


def _normalize_url(url: str) -> str:
    text = str(url or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or "").removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


def _set_context(session: Session, *, tenant_id: str, conversation_id: str, product_id: str, source: str) -> None:
    if conversation_id and product_id:
        set_active_product(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            product_id=product_id,
            source=source,
        )


def crv2_resolve_reply_to_product(
    session: Session,
    *,
    tenant_id: str,
    channel: str,
    reply_to_message_id: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    product_id = resolve_reply_to_product(
        session,
        tenant_id=tenant_id,
        channel=channel,
        reply_to_message_id=reply_to_message_id,
    )
    if not product_id:
        return {"tool": "resolve_reply_to_product", "ok": True, "match": None}
    row = ProductsRepository(session).get_product(tenant_id=tenant_id, product_id=product_id)
    if row is None or not is_customer_searchable(row.availability):
        return {"tool": "resolve_reply_to_product", "ok": True, "match": None}
    if conversation_id:
        _set_context(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            product_id=product_id,
            source="reply_to_product",
        )
    return {"tool": "resolve_reply_to_product", "ok": True, "resolver": "reply_to", "match": slim_product_match(row)}


def crv2_get_active_product_context(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    ctx = get_active_product(session, tenant_id=tenant_id, conversation_id=conversation_id)
    if not ctx:
        return {"tool": "get_active_product_context", "ok": True, "active_product_id": None}
    row = ProductsRepository(session).get_product(
        tenant_id=tenant_id,
        product_id=str(ctx.get("active_product_id") or ""),
    )
    if row is None or not is_customer_searchable(row.availability):
        return {"tool": "get_active_product_context", "ok": True, "active_product_id": None}
    return {
        "tool": "get_active_product_context",
        "ok": True,
        "active_product_id": row.id,
        "source": ctx.get("source"),
        "product": slim_product_match(row),
    }


def crv2_search_product_by_title(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
    use_luna_fallback: bool = False,
    conversation_id: str | None = None,
    title_offset: int = 0,
) -> dict[str, Any]:
    matches = search_product_by_title(session, tenant_id=tenant_id, title=title, limit=limit)
    resolver = "deterministic"
    extra_luna_agent = False
    titles_fallback: dict[str, Any] | None = None
    if not matches and use_luna_fallback:
        from services.products.luna_title_resolver import resolve_product_titles_with_luna

        luna_matches = _run_async(
            resolve_product_titles_with_luna(session, tenant_id=tenant_id, query=title, limit=limit)
        )
        extra_luna_agent = True
        if luna_matches:
            matches = luna_matches
            resolver = "luna"
    if not matches and not use_luna_fallback:
        titles_fallback = list_active_product_titles(session, tenant_id=tenant_id, offset=title_offset)
        resolver = "titles_fallback"
    slim = [slim_product_match(row) for row in matches]
    if len(slim) == 1 and conversation_id:
        _set_context(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            product_id=str(slim[0]["id"]),
            source="luna_title_match" if resolver == "luna" else "title_search",
        )
    out: dict[str, Any] = {
        "tool": "search_product_by_title",
        "query": title,
        "resolver": resolver,
        "match_count": len(slim),
        "matches": slim,
        "extra_luna_agent": extra_luna_agent,
        "full_catalog": False,
    }
    if titles_fallback is not None:
        out["titles_fallback"] = titles_fallback
    return out


def crv2_list_product_titles(
    session: Session,
    *,
    tenant_id: str,
    offset: int = 0,
    limit: int = 80,
) -> dict[str, Any]:
    page = list_active_product_titles(session, tenant_id=tenant_id, offset=offset, limit=limit)
    return {"tool": "list_product_titles", "ok": True, "full_catalog": False, **page}


def crv2_get_product_details(
    session: Session,
    *,
    tenant_id: str,
    product_id: str,
    conversation_id: str | None = None,
    context_source: str | None = None,
) -> dict[str, Any]:
    row = ProductsRepository(session).get_product(tenant_id=tenant_id, product_id=product_id)
    if row is None:
        return {"tool": "get_product_details", "ok": False, "error": "not_found"}
    if not is_customer_searchable(row.availability):
        return {"tool": "get_product_details", "ok": False, "error": "not_customer_facing"}
    if conversation_id and context_source:
        _set_context(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            product_id=product_id,
            source=context_source,
        )
    return {"tool": "get_product_details", "ok": True, "product": product_details_for_tera(row)}


def crv2_get_product_images(session: Session, *, tenant_id: str, product_id: str) -> dict[str, Any]:
    row = ProductsRepository(session).get_product(tenant_id=tenant_id, product_id=product_id)
    if row is None:
        return {"tool": "get_product_images", "ok": False, "error": "not_found"}
    if not is_customer_searchable(row.availability):
        return {"tool": "get_product_images", "ok": False, "error": "not_customer_facing"}
    images = [
        {
            "media_id": img.media_id,
            "sort_order": img.sort_order,
            "mime": (load_media_meta(tenant_id=tenant_id, media_id=img.media_id) or {}).get("mime"),
        }
        for img in sorted(row.images or [], key=lambda i: i.sort_order)
    ]
    return {"tool": "get_product_images", "ok": True, "product_id": product_id, "images": images}


def crv2_find_product_by_url(
    session: Session,
    *,
    tenant_id: str,
    url: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    needle = _normalize_url(url)
    if not needle:
        return {"tool": "find_product_by_url", "ok": False, "error": "empty_url"}
    row = ProductsRepository(session).find_by_link_url(tenant_id=tenant_id, normalized_url=needle)
    if row is None or not is_customer_searchable(row.availability):
        return {"tool": "find_product_by_url", "ok": True, "match": None}
    if conversation_id:
        _set_context(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            product_id=row.id,
            source="url_match",
        )
    return {"tool": "find_product_by_url", "ok": True, "match": slim_product_match(row)}


def _clamp_image_top_k(top_k: int) -> int:
    try:
        value = int(top_k)
    except (TypeError, ValueError):
        value = TOP_K_DEFAULT
    return min(max(value, 3), 8)


def crv2_find_product_by_image(
    session: Session,
    *,
    tenant_id: str,
    image_bytes: bytes,
    top_k: int = TOP_K_DEFAULT,
    conversation_id: str | None = None,
    known_title: str = "",
) -> dict[str, Any]:
    known = str(known_title or "").strip()
    if known:
        titled = crv2_search_product_by_title(
            session,
            tenant_id=tenant_id,
            title=known,
            limit=5,
            use_luna_fallback=False,
            conversation_id=conversation_id,
        )
        if int(titled.get("match_count") or 0) >= 1:
            return {
                "tool": "find_product_by_image",
                "ok": True,
                "resolver": "name_first",
                "vision_used": False,
                "candidate_count": 0,
                "match_count": titled["match_count"],
                "matches": titled["matches"],
                "ambiguous": int(titled["match_count"]) != 1,
            }
    candidates = find_image_candidates(
        session,
        tenant_id=tenant_id,
        query_bytes=image_bytes,
        top_k=_clamp_image_top_k(top_k),
        similarity_threshold=SIMILARITY_THRESHOLD,
    )
    repo = ProductsRepository(session)
    resolved_id: str | None = None
    resolver = "vector_search"

    if len(candidates) == 1 and float(candidates[0].get("similarity") or 0) >= 0.95:
        resolved_id = str(candidates[0].get("product_id") or "")
        resolver = "exact_or_strong_phash"
    elif candidates:
        enriched = []
        for cand in candidates:
            row = repo.get_product(tenant_id=tenant_id, product_id=str(cand.get("product_id") or ""))
            if row is None or not is_customer_searchable(row.availability):
                continue
            enriched.append({**cand, "product_name": row.name})
        if len(enriched) == 1 and float(enriched[0].get("similarity") or 0) >= SIMILARITY_THRESHOLD:
            resolved_id = str(enriched[0].get("product_id") or "")
            resolver = "single_strong_candidate"
        elif len(enriched) > 1:
            rerank = _run_async(
                vision_rerank_candidates(
                    tenant_id=tenant_id,
                    query_bytes=image_bytes,
                    candidates=enriched,
                    media_loader=lambda media_id: load_media_bytes(tenant_id=tenant_id, media_id=media_id),
                )
            )
            if rerank.get("resolved"):
                resolved_id = str(rerank.get("product_id") or "") or None
                resolver = "vision_rerank"

    matches: list[dict[str, Any]] = []
    if resolved_id:
        row = repo.get_product(tenant_id=tenant_id, product_id=resolved_id)
        if row is not None and is_customer_searchable(row.availability):
            matches = [slim_product_match(row)]
            if conversation_id:
                _set_context(
                    session,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    product_id=resolved_id,
                    source="image_match",
                )
    else:
        for cand in candidates:
            row = repo.get_product(tenant_id=tenant_id, product_id=str(cand.get("product_id") or ""))
            if row is not None and is_customer_searchable(row.availability):
                payload = slim_product_match(row)
                payload["similarity"] = cand.get("similarity")
                matches.append(payload)

    return {
        "tool": "find_product_by_image",
        "ok": True,
        "resolver": resolver,
        "vision_used": resolver == "vision_rerank",
        "candidate_count": len(candidates),
        "match_count": len(matches),
        "matches": matches,
        "ambiguous": bool(candidates) and not resolved_id,
    }


def crv2_active_product_context(active_product_id: str | None) -> dict[str, Any]:
    return {"active_product_id": (active_product_id or "").strip() or None}
