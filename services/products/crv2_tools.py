"""Customer Reply V2 product tools — tenant injected server-side."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from services.products.image_index import find_image_candidates
from services.products.media import load_media_meta
from services.products.repository import ProductsRepository
from services.products.schemas import product_to_dict
from services.products.search import search_product_by_title


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


def crv2_search_product_by_title(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
    use_luna_fallback: bool = False,
) -> dict[str, Any]:
    matches = search_product_by_title(
        session,
        tenant_id=tenant_id,
        title=title,
        limit=limit,
    )
    resolver = "deterministic"
    if not matches and use_luna_fallback:
        from services.products.luna_title_resolver import resolve_product_titles_with_luna

        luna_matches = _run_async(
            resolve_product_titles_with_luna(
                session,
                tenant_id=tenant_id,
                query=title,
                limit=limit,
            )
        )
        if luna_matches:
            matches = luna_matches
            resolver = "luna"
    return {
        "tool": "search_product_by_title",
        "query": title,
        "resolver": resolver,
        "match_count": len(matches),
        "matches": matches,
    }


def crv2_get_product_details(
    session: Session,
    *,
    tenant_id: str,
    product_id: str,
) -> dict[str, Any]:
    repo = ProductsRepository(session)
    row = repo.get_product(tenant_id=tenant_id, product_id=product_id)
    if row is None:
        return {"tool": "get_product_details", "ok": False, "error": "not_found"}
    return {"tool": "get_product_details", "ok": True, "product": product_to_dict(row)}


def crv2_get_product_images(
    session: Session,
    *,
    tenant_id: str,
    product_id: str,
) -> dict[str, Any]:
    repo = ProductsRepository(session)
    row = repo.get_product(tenant_id=tenant_id, product_id=product_id)
    if row is None:
        return {"tool": "get_product_images", "ok": False, "error": "not_found"}
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
) -> dict[str, Any]:
    """URL lookup — 0 AI credits (deterministic DB match)."""
    needle = _normalize_url(url)
    if not needle:
        return {"tool": "find_product_by_url", "ok": False, "error": "empty_url"}
    repo = ProductsRepository(session)
    row = repo.find_by_link_url(tenant_id=tenant_id, normalized_url=needle)
    if row is None:
        return {"tool": "find_product_by_url", "ok": True, "match": None}
    return {"tool": "find_product_by_url", "ok": True, "match": product_to_dict(row)}


def crv2_find_product_by_image(
    session: Session,
    *,
    tenant_id: str,
    image_bytes: bytes,
    top_k: int = 10,
) -> dict[str, Any]:
    """Phase 1 stub — checksum exact match only; vision rerank deferred to Phase 2."""
    candidates = find_image_candidates(
        tenant_id=tenant_id,
        query_bytes=image_bytes,
        top_k=min(max(top_k, 8), 12),
    )
    repo = ProductsRepository(session)
    matches: list[dict[str, Any]] = []
    for cand in candidates:
        row = repo.get_product(tenant_id=tenant_id, product_id=str(cand.get("product_id") or ""))
        if row is not None:
            matches.append(product_to_dict(row))
    return {
        "tool": "find_product_by_image",
        "ok": True,
        "phase": "stub_checksum_only",
        "candidate_count": len(candidates),
        "matches": matches,
        "note": "vision_rerank_phase_2",
    }


def crv2_active_product_context(active_product_id: str | None) -> dict[str, Any]:
    return {"active_product_id": (active_product_id or "").strip() or None}
